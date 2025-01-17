"""
Evaluate 3D shape classification.
"""
import argparse
import importlib
import logging
import os
import sys

import numpy as np
import torch
from compat_loader import CompatLoader3DCls as Compat
from tqdm import tqdm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = BASE_DIR
sys.path.append(os.path.join(ROOT_DIR, "models"))


def parse_args():
    """
    Parse input arguments.
    """
    parser = argparse.ArgumentParser("Testing")
    parser.add_argument(
        "--use_cpu", action="store_true", default=False, help="use cpu mode"
    )
    parser.add_argument("--gpu", type=str, default="0", help="specify gpu device")
    parser.add_argument(
        "--batch_size", type=int, default=24, help="batch size in training"
    )
    parser.add_argument(
        "--num_category",
        default=42,
        type=int,
        choices=[10, 40],
        help="training on ModelNet10/40",
    )
    parser.add_argument("--num_point", type=int, default=1024, help="Point Number")
    parser.add_argument("--log_dir", type=str, required=True, help="Experiment root")
    parser.add_argument(
        "--use_normals", action="store_true", default=False, help="use normals"
    )
    parser.add_argument(
        "--use_uniform_sample",
        action="store_true",
        default=False,
        help="use uniform sampiling",
    )
    parser.add_argument(
        "--num_votes",
        type=int,
        default=1,
        help="Aggregate classification scores with voting",
    )
    parser.add_argument("--data_name", type=str, default="coarse", help="data_name")

    return parser.parse_args()


def inference(model, loader, num_class=40, vote_num=1):
    mean_correct = []
    classifier = model.eval()
    class_acc = np.zeros((num_class, 3))

    for points in tqdm(loader, total=len(loader)):
        if not args.use_cpu:
            points = points.cuda()

        points = points.transpose(2, 1)
        # vote_pool = torch.zeros(target.size()[0], num_class).cuda()

        pred, _ = classifier(points)
        # for _ in range(vote_num):
        #     pred, _ = classifier(points)
        #     vote_pool += pred
        # pred = vote_pool / vote_num
        pred_choice = pred.data.max(1)[1]
        print("pred_choice", pred_choice)
        # for cat in np.unique(target.cpu()):
        #     classacc = (
        #         pred_choice[target == cat]
        #         .eq(target[target == cat].long().data)
        #         .cpu()
        #         .sum()
        #     )
        #     class_acc[cat, 0] += classacc.item() / float(
        #         points[target == cat].size()[0]
        #     )
        #     class_acc[cat, 1] += 1
        # correct = pred_choice.eq(target.long().data).cpu().sum()
        # mean_correct.append(correct.item() / float(points.size()[0]))

    # class_acc[:, 2] = class_acc[:, 0] / class_acc[:, 1]
    # class_acc = np.mean(class_acc[:, 2])
    # instance_acc = np.mean(mean_correct)
    return pred_choice


def main(args):
    def log_string(str):
        logger.info(str)
        print(str)

    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    experiment_dir = "log/classification_mn40/" + args.log_dir

    # Logging
    args = parse_args()
    logger = logging.getLogger("Model")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = logging.FileHandler("%s/eval.txt" % experiment_dir)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    log_string("PARAMETER ...")
    log_string(args)

    # Dataloader
    log_string("Load dataset ...")
    root = os.path.join(os.getcwd(), "data/" + args.data_name + "_grained/")
    INFERENCE_DATASET = Compat(
        data_root=root, num_points=args.num_point, split="test", transform=None, seg_mode="part"
    )
    inferenceDataLoader = torch.utils.data.DataLoader(
        INFERENCE_DATASET, batch_size=args.batch_size, shuffle=False, num_workers=10
    )

    # Loading the models
    num_class = args.num_category
    model_name = os.listdir(experiment_dir + "/logs")[0].split(".")[0]
    model = importlib.import_module(model_name)

    classifier = model.get_model(num_class, normal_channel=args.use_normals)
    if not args.use_cpu:
        classifier = classifier.cuda()

    checkpoint = torch.load(str(experiment_dir) + "/checkpoints/best_model.pth")
    classifier.load_state_dict(checkpoint["model_state_dict"])

    with torch.no_grad():
        instance_acc_avg, class_acc_avg = 0.0, 0.0
        # for _ in range(5):
        predicted_class = inference(
            classifier.eval(),
            inferenceDataLoader,
            vote_num=args.num_votes,
            num_class=num_class,
        )
        log_string(
            "Test Instance Accuracy: %f, Class Accuracy: %f"
            % (instance_acc, class_acc)
        )
        instance_acc_avg += instance_acc
        class_acc_avg += class_acc
        # print("Running 5 times average: ", instance_acc_avg / 5.0, class_acc_avg / 5.0)


if __name__ == "__main__":
    args = parse_args()
    main(args)
