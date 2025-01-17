import torch
import numpy as np
import h5py

# OUTDIR= ""

# Modified from https://colab.research.google.com/drive/1wr0CUhict2xn8umvCh7da3iX0ku058h4#scrollTo=FCrax0nI67xQ
def project_to_2D(pointcloud, cam_parameters):
    """
    Project 3D pointcloud to 2D image plane.
    """
    K, M = cam_parameters.chunk(2, axis=0)
    proj_matrix = K @ M
    pc = np.concatenate([pointcloud, np.ones([pointcloud.shape[0], 1])], axis=1).T

    # Applying the projection matrix
    pc = np.matmul(proj_matrix, pc)
    pc_final = pc/pc[2]

    return pc_final.T

def valid_pixel(x, y, imsize):
    return x >= 0 and y >= 0 and x < imsize and y < imsize 

def get_logits_from2d(batch_points, logits_2d, cam_parameters):
    logits_3d = None
    OOB_LOGIT = torch.zeros(logits_2d.shape[1]).cpu()
    imsize = logits_2d.shape[-1]
    for i, points in enumerate(batch_points):
        pixels = np.rint(project_to_2D(points, cam_parameters[i])[:, :-2])
        logit = torch.stack([ logits_2d[i,:,int(x), int(y)] if valid_pixel(x, y, imsize) else OOB_LOGIT for x, y in pixels])
        if logits_3d == None:
            logits_3d = logit.unsqueeze(0)
        else:
            logits_3d = torch.cat((logits_3d, logit.unsqueeze(0)), dim=0)
    return logits_3d


def logits_to_prediction(logits):
    return torch.argmax(logits, -1)

def get_key(sid, stid):
    return "{}_{}".format(sid, stid)

def update_part_logits(saved_results, shape_ids, style_ids, fused_logits):
    style_ids = style_ids.cpu().data.numpy()
    for i, shape_id in enumerate(shape_ids):
        key = get_key(shape_id, style_ids[i])
        accu_logits = saved_results.get(key, torch.zeros((fused_logits.shape)).cpu())
        saved_results[key] = accu_logits + fused_logits[i]
    return saved_results

def update_each_logits(saved_results, shape_ids, style_ids, logits):
    n_views = 8
    style_ids = style_ids.cpu().data.numpy()
    for i, shape_id in enumerate(shape_ids):
        key = get_key(shape_id, style_ids[i])
        if key not in saved_results:
            saved_results[key] = logits[i].unsqueeze(0)
        else:
            saved_results[key] = torch.cat((saved_results[key], logits[i].unsqueeze(0)), dim=0)
        assert saved_results[key].shape[0] <= n_views + 1
        if saved_results[key].shape[0] == n_views:
            # # save all
            # saved_results[key] = torch.cat((saved_results[key], torch.sum(saved_results[key], dim=0).unsqueeze(0)), dim=0) # TODO: need to unsqueeze?
            # assert saved_results[key][8][3][12] == sum([saved_results[key][j][3][12] for j in range(n_views)])
            # saved_results[key] = saved_results[key].transpose(1,0)

            # save sum logits
            saved_results[key] = torch.sum(saved_results[key], dim=0)

    return saved_results

def update_predictions(shape_ids, style_ids, predicted_cls, predicted_parts, predicted_mats, saved_cls_predictions, saved_part_predictions, saved_mat_predictions):
    style_ids = style_ids.cpu().data.numpy()
    for i, shape_id in enumerate(shape_ids):
        key = get_key(shape_id, style_ids[i])
        if key in saved_cls_predictions:
            continue
        saved_cls_predictions[key] = predicted_cls[i]
        if saved_part_predictions != None:
            saved_part_predictions[key] = predicted_parts[i]
        if saved_mat_predictions != None:
            saved_mat_predictions[key] = predicted_mats[i]
    return saved_cls_predictions, saved_part_predictions, saved_mat_predictions

def get_fused_prediction(fused_logits, predicted3d):
    fused_prediction = logits_to_prediction(fused_logits)
    fused_prediction -= torch.ones(fused_prediction.shape, dtype=int)
    fused_prediction_np = fused_prediction.numpy()
    fail2d_mask = fused_prediction_np == -1
    fused_prediction_np[fail2d_mask] = predicted3d[fail2d_mask]
    return fused_prediction_np

### ========= For submission

def init_submission_file(filename, fieldname):
    N_TEST_SHAPES = 12560
    with h5py.File(filename, 'w') as file:
        file.create_dataset(fieldname,
                                    shape=(N_TEST_SHAPES),
                                    dtype='uint8')

def save_submission(submission, cls, parts, mats, test_order_map):
    submission.update_batched('shape_preds', cls, test_order_map)
    if parts != None:
        submission.update_batched('part_labels', parts, test_order_map)
    if mats != None:
        submission.update_batched('mat_labels', mats, test_order_map)

def save_features(featureFile, feature_parts, feature_mats, order_map):
    if feature_parts != None:
        featureFile.update_batched('partseg_2dlogits', feature_parts, order_map)
    if feature_mats != None:
        featureFile.update_batched('matseg_2dlogits', feature_mats, order_map)
# def update_submission(filename, column_name, predictions, test_order_map):
#     # Open the HDF5 file in 'a' (append) mode
#     with h5py.File(filename, 'a') as file:
#         for key, val in predictions.items():
#             index = test_order_map[key]
#             file[column_name][index] = val

#### ========== For feature vector.

def init_predicted_files():
    create_prediction("shape_dict.hdf5", 'shape_preds')
    create_prediction("parts_dict.hdf5", 'part_labels')
    create_prediction("part_logits_dict.hdf5", 'part_logits')

def save_predictions_checkpoint(cls, parts, parts_logits):
    save_predictions("shape_dict.hdf5", cls)
    save_predictions("parts_dict.hdf5", parts)
    save_predictions("part_logits_dict.hdf5", parts_logits)


def create_prediction(filename, fieldname):
    NTEST = 1004800
    N_COMP = 10
    with h5py.File(filename, 'w') as file:
        file.create_dataset(fieldname,
                                    shape=(NTEST * N_COMP),
                                    dtype='uint8')

def save_predictions(filename, predictions, st_id):
    # Open the HDF5 file in 'a' (append) mode
    with h5py.File(filename, 'a') as file:
        for key, val in predictions.items():
            # print(k_str)
            file[k_str] = val.cpu().data.numpy()


