import os
import random
import numpy as np
import argparse
import torch
import time
from torchvision.transforms import ToTensor
from utils.meters import AverageValueMeter
from utils.weights import load_from_weights
from utils import check_dir, set_random_seed, accuracy, mIoU, get_logger, save_in_log
from models.att_segmentation import AttSegmentator
#from torch.utils.tensorboard import SummaryWriter
from data.transforms import get_transforms_binary_segmentation
from models.pretraining_backbone import ResNet18Backbone
from data.segmentation import DataReaderSingleClassSemanticSegmentationVector, DataReaderSemanticSegmentationVector
import matplotlib.pyplot as plt
import pandas as pd

set_random_seed(0)
global_step = 0

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('data_folder', type=str, help="folder containing the data")
    parser.add_argument('--pretrained_model_path', type=str, default='')
    parser.add_argument('--output-root', type=str, default='results')
    parser.add_argument('--lr', type=float, default=0.001, help='learning rate')
    parser.add_argument('--bs', type=int, default=32, help='batch_size')
    parser.add_argument('--att', type=str, default='sdotprod', help='Type of attention. Choose from {additive, cosine, dotprod, sdotprod}')
    parser.add_argument('--size', type=int, default=256, help='image size')
    parser.add_argument('--snapshot-freq', type=int, default=5, help='how often to save models')
    parser.add_argument('--exp-suffix', type=str, default="")
    args = parser.parse_args()

    hparam_keys = ["lr", "bs", "att"]
    args.exp_name = "_".join(["{}{}".format(k, getattr(args, k)) for k in hparam_keys])

    args.exp_name += "_{}".format(args.exp_suffix)

    args.output_folder = check_dir(os.path.join(args.output_root, 'dt_attseg', args.exp_name))
    args.model_folder = check_dir(os.path.join(args.output_folder, "models"))
    args.logs_folder = check_dir(os.path.join(args.output_folder, "logs"))
    args.plots_folder = check_dir(os.path.join(args.output_folder, "plots"))

    return args


def main(args):
    # Logging to the file and stdout
    logger = get_logger(args.output_folder, args.exp_name)
    img_size = (args.size, args.size)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('#### This is the device used: ', device, '####')

    # model
    pretrained_model = ResNet18Backbone(False).to(device)
    # TODO: Complete the documentation for AttSegmentator model
    #raise NotImplementedError("TODO: Build model AttSegmentator model")
    model = AttSegmentator(5, pretrained_model.features, att_type = 'dotprod', img_size = img_size ).to(device)

    if os.path.isfile(args.pretrained_model_path):
        model = load_from_weights(model, args.pretrained_model_path, logger)

    # dataset
    data_root = args.data_folder
    train_transform, val_transform, train_transform_mask, val_transform_mask = get_transforms_binary_segmentation(args)
    vec_transform = ToTensor()
    train_data = DataReaderSingleClassSemanticSegmentationVector(
        os.path.join(data_root, "imgs/train2014"),
        os.path.join(data_root, "aggregated_annotations_train_5classes.json"),
        transform=train_transform,
        vec_transform=vec_transform,
        target_transform=train_transform_mask
    )
    # Note that the dataloaders are different.
    # During validation we want to pass all the semantic classes for each image
    # to evaluate the performance.
    val_data = DataReaderSemanticSegmentationVector(
        os.path.join(data_root, "imgs/val2014"),
        os.path.join(data_root, "aggregated_annotations_val_5classes.json"),
        transform=val_transform,
        vec_transform=vec_transform,
        target_transform=val_transform_mask
    )

    train_loader = torch.utils.data.DataLoader(train_data, batch_size=args.bs, shuffle=True,
                                               num_workers=6, pin_memory=True, drop_last=True)
    val_loader = torch.utils.data.DataLoader(val_data, batch_size=1, shuffle=False,
                                             num_workers=6, pin_memory=True, drop_last=False)


    # TODO: loss
    criterion = torch.nn.CrossEntropyLoss()
    # TODO: SGD optimizer (see pretraining)
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, momentum=0.9, weight_decay=1e-4)
    #raise NotImplementedError("TODO: loss function and SGD optimizer")

    expdata = "  \n".join(["{} = {}".format(k, v) for k, v in vars(args).items()])
    logger.info(expdata)
    logger.info('train_data {}'.format(train_data.__len__()))
    logger.info('val_data {}'.format(val_data.__len__()))

    best_val_loss = np.inf
    best_val_miou = 0.0

    train_loss_list = []
    train_iou_list = []
    val_loss_list = []
    val_iou_list = []
    for epoch in range(100):
        logger.info("Epoch {}".format(epoch))
        train_loss, train_iou = train(train_loader, model, criterion, optimizer, logger, device, epoch)
        val_loss, val_iou = validate(val_loader, model, criterion, logger, device, epoch)

        # TODO save model
        #raise NotImplementedError("TODO: implement the code for saving the model")
        train_loss_list.append(train_loss)
        train_iou_list.append(train_iou)
        val_loss_list.append(val_loss)
        val_iou_list.append(val_iou)

        if val_iou > best_val_miou:
            best_val_miou = val_iou
            save_model(model, optimizer, args, epoch+1, val_loss, val_iou, logger, best_iou=True, best_loss = False)
        
        elif val_loss < best_val_loss:
            best_val_loss = val_loss
            save_model(model, optimizer, args, epoch+1, val_loss, val_iou, logger, best_iou=False, best_loss = True)
        
        elif ((epoch+1)%10 == 0):
            save_model(model, optimizer, args, epoch+1, val_loss, val_iou, logger, best_iou=False, best_loss = False)
        
        # save the data
        save_fig (train_loss_list, 'train_loss')
        save_fig (train_iou_list, 'train_iou')
        save_fig (val_loss_list, 'val_loss')
        save_fig (val_iou_list, 'val_iou')

        pd.DataFrame({'train_loss':train_loss_list}).to_csv(os.path.join(args.plots_folder, 'train_loss.csv'), index= False)
        pd.DataFrame({'train_iou':train_iou_list}).to_csv(os.path.join(args.plots_folder, 'train_iou.csv'), index= False)
        pd.DataFrame({'val_loss':val_loss_list}).to_csv(os.path.join(args.plots_folder, 'val_loss.csv'), index= False)
        pd.DataFrame({'val_iou':val_iou_list}).to_csv(os.path.join(args.plots_folder, 'val_iou.csv'), index= False)




def train(loader, model, criterion, optimizer, logger, device, epoch = 0):
    logger.info("Training")
    model.train()

    loss_meter = AverageValueMeter()
    iou_meter = AverageValueMeter()
    time_meter = AverageValueMeter()
    steps_per_epoch = len(loader.dataset) / loader.batch_size

    start_time = time.time()
    batch_time = time.time()
    for idx, (img, v_class, label) in enumerate(loader):
        img = img.to(device)
        v_class = v_class.float().to(device).squeeze()
        logits, alphas = model(img, v_class, out_att=True)
        logits = logits.squeeze()
        labels = (torch.nn.functional.interpolate(label.to(device), size=logits.shape[-2:]).squeeze(1)*256).long()
        loss = criterion(logits, labels)
        iou = mIoU(logits, labels)

        # backward
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        loss_meter.add(loss.item())
        iou_meter.add(iou)
        time_meter.add(time.time()-batch_time)

        if idx % 200 == 0: #or idx == len(loader)-1:
            text_print = "Epoch {} Avg loss = {:.4f} mIoU = {:.4f} Time {:.2f} (Total:{:.2f}) Progress {}/{}".format(
                        epoch, loss_meter.mean, iou_meter.mean, time_meter.mean, time.time()-start_time, idx, int(steps_per_epoch))
            logger.info(text_print)
            # loss_meter.reset()
            # iou_meter.reset()

        batch_time = time.time()
    time_txt = "batch time: {:.2f} total time: {:.2f}".format(time_meter.mean, time.time()-start_time)
    logger.info(time_txt)
    train_txt = "train_loss: {:.2f} train_IoU : {:.2f}".format(loss_meter.mean, iou_meter.mean)
    logger.info(train_txt)
    return loss_meter.mean, iou_meter.mean

def validate(loader, model, criterion, logger, device, epoch=0):
    logger.info("Validating Epoch {}".format(epoch))
    model.eval()

    loss_meter = AverageValueMeter()
    iou_meter = AverageValueMeter()

    start_time = time.time()
    for idx, (img, v_class, label) in enumerate(loader):
        with torch.no_grad():
            img = img.squeeze(0).to(device)
            v_class = v_class.float().to(device).squeeze()
            logits, alphas = model(img, v_class, out_att=True)
            label = label.squeeze(0).unsqueeze(1)
            labels = (torch.nn.functional.interpolate(label.to(device), size=logits.shape[-2:]).squeeze(1)*256).long()
            loss = criterion(logits, labels)
            iou = mIoU(logits, labels)

            loss_meter.add(loss.item())
            iou_meter.add(iou)

    text_print = "Epoch {} Avg loss = {:.4f} mIoU = {:.4f} Time {:.2f}".format(epoch, loss_meter.mean, iou_meter.mean, time.time()-start_time)
    logger.info(text_print)
    val_txt = "val_loss: {:.2f} val_IoU : {:.2f}".format(loss_meter.mean, iou_meter.mean)
    logger.info(val_txt)
    return loss_meter.mean, iou_meter.mean

def save_model(model, optimizer, args, epoch, val_loss, val_iou, logger, best_iou=False, best_loss = False):
    # save model
    if best_iou:
        add_text_best = 'BEST_iou'
    elif best_loss:
        add_text_best = 'BEST_loss'
    else:
        add_text_best = ''
    logger.info('==> Saving '+add_text_best+' ... epoch {} loss {:.03f} miou {:.03f} '.format(epoch, val_loss, val_iou))
    state = {
        'opt': args,
        'epoch': epoch,
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'loss': val_loss,
        'miou': val_iou
    }
    if best_iou:
        torch.save(state, os.path.join(args.model_folder, 'ckpt_' +add_text_best+ '_{}.pth'.format(epoch)))
    elif best_loss:
        torch.save(state, os.path.join(args.model_folder, 'ckpt_' +add_text_best+ '_{}.pth'.format(epoch)))
    else:
        torch.save(state, os.path.join(args.model_folder, 'ckpt_epoch {}_loss {:.03f}_miou {:.03f}.pth'.format(epoch, val_loss, val_iou)))


def save_fig (train_list, name):
    plt.figure()
    plt.plot(train_list)
    plt.xlabel('epochs')
    plt.ylabel(name)
    if not os.path.exists(args.plots_folder):
        os.makedirs(args.plots_folder)
    path = os.path.join(args.plots_folder, name+'.png')
    plt.savefig(path)

if __name__ == '__main__':
    args = parse_arguments()
    main(args)
