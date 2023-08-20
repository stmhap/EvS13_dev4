"""
Implementation of Yolo Loss Function similar to the one in Yolov3 paper,
the difference from what I can tell is I use CrossEntropy for the classes
instead of BinaryCrossEntropy.
"""

import torch
import torch.nn as nn
#from pytorch_lightning import LightningModule
from utils import intersection_over_union


class YoloLoss(nn.Module):
    def __init__(self, lambda_noobj=10, lambda_box=10):
        super(YoloLoss, self).__init__()
        self.mse = nn.MSELoss()
        self.bce = nn.BCEWithLogitsLoss()
        self.entropy = nn.CrossEntropyLoss()
        self.sigmoid = nn.Sigmoid()

        # Constants signifying how much to pay for each respective part of the loss
        self.lambda_class = 1
        self.lambda_noobj = lambda_noobj
        self.lambda_obj = 1
        self.lambda_box = lambda_box

    def calculate_loss(self, predictions, target, anchors):
        # Check where obj and noobj (we ignore if target == -1)
        obj = target[..., 0] == 1  # in paper this is Iobj_i
        noobj = target[..., 0] == 0  # in paper this is Inoobj_i

        # ======================= #
        #   FOR NO OBJECT LOSS    #
        # ======================= #

        no_object_loss = self.bce(
            (predictions[..., 0:1][noobj]), (target[..., 0:1][noobj]),
        )

        # ==================== #
        #   FOR OBJECT LOSS    #
        # ==================== #

        anchors = anchors.reshape(1, 3, 1, 1, 2)
        box_preds = torch.cat([self.sigmoid(predictions[..., 1:3]), torch.exp(predictions[..., 3:5]) * anchors], dim=-1)
        ious = intersection_over_union(box_preds[obj], target[..., 1:5][obj]).detach()
        object_loss = self.mse(self.sigmoid(predictions[..., 0:1][obj]), ious * target[..., 0:1][obj])

        # ======================== #
        #   FOR BOX COORDINATES    #
        # ======================== #

        predictions[..., 1:3] = self.sigmoid(predictions[..., 1:3])  # x,y coordinates
        target[..., 3:5] = torch.log(
            (1e-16 + target[..., 3:5] / anchors)
        )  # width, height coordinates
        box_loss = self.mse(predictions[..., 1:5][obj], target[..., 1:5][obj])

        # ================== #
        #   FOR CLASS LOSS   #
        # ================== #

        class_loss = self.entropy(
            (predictions[..., 5:][obj]), (target[..., 5][obj].long()),
        )

        return (
            self.lambda_box * box_loss
            + self.lambda_obj * object_loss
            + self.lambda_noobj * no_object_loss
            + self.lambda_class * class_loss
        )

    def forward(self, predictions, target, anchors):
        # return self.calculate(predictions.to(self.device), target.to(self.device), anchors.to(self.device))
        return self.calculate_loss(predictions, target, anchors)


class YoloLossCumulative(nn.Module):
    def __init__(self, scaled_anchors, lambda_noobj=10, lambda_box=10):
        super(YoloLossCumulative, self).__init__()
        self.yolo_loss = YoloLoss(lambda_noobj, lambda_box)
        self.register_buffer("scaled_anchors", scaled_anchors)

    def forward(self, predictions, target):
        combined_loss = 0
        for i in range(len(target)):
            combined_loss += self.yolo_loss(predictions[i], target[i], self.scaled_anchors[i])
        return combined_loss
