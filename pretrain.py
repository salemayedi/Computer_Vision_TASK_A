import os
import numpy as np
import argparse
import torch
from pprint import pprint
from data.pretraining import DataReaderPlainImg, custom_collate
from data.transforms import get_transforms_pretraining
from utils import check_dir, accuracy, get_logger
from models.pretraining_backbone import ResNet18Backbone
import matplotlib.pyplot as plt


global_step = 0


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('data_folder', type=str, help="folder containing the data (crops)")
    parser.add_argument('--weights-init', type=str,
                        default="random")
    parser.add_argument('--output-root', type=str, default='results')
    parser.add_argument('--lr', type=float, default=0.005, help='learning rate')
    parser.add_argument('--bs', type=int, default=8, help='batch_size')
    parser.add_argument("--size", type=int, default=256, help="size of the images to feed the network")
    parser.add_argument('--snapshot-freq', type=int, default=1, help='how often to save models')
    parser.add_argument('--exp-suffix', type=str, default="", help="string to identify the experiment")
    args = parser.parse_args()

    hparam_keys = ["lr", "bs", "size"]
    args.exp_name = "_".join(["{}{}".format(k, getattr(args, k)) for k in hparam_keys])

    args.exp_name += "_{}".format(args.exp_suffix)

    args.output_folder = check_dir(os.path.join(args.output_root, 'pretrain', args.exp_name))
    args.model_folder = check_dir(os.path.join(args.output_folder, "models"))
    args.logs_folder = check_dir(os.path.join(args.output_folder, "logs"))

    return args


def main(args):
    # Logging to the file and stdout
    logger = get_logger(args.output_folder, args.exp_name)

    # Device configuration
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # build model and load weights
    model = ResNet18Backbone(pretrained=False).to(device)
    
    model.load_state_dict(torch.load(args.weights_init, map_location = device) , strict=False)
    #raise NotImplementedError("TODO: load weight initialization")
    


    # load dataset
    data_root = args.data_folder
    train_transform, val_transform = get_transforms_pretraining(args)
    train_data = DataReaderPlainImg(os.path.join(data_root, str(args.size), "train"), transform=train_transform)
    print(' hereeeeeeeeeeeeeeeeeeee', type(train_data.__getitem__(5)[0][0]))
    plt.imshow(train_data.__getitem__(5)[0][0].numpy().transpose(2,1,0), interpolation='nearest')
    plt.show()
    plt.imshow(train_data.__getitem__(100)[0][0].numpy()[2])
    plt.show()
    plt.imshow(train_data.__getitem__(100)[0][1].numpy()[2])
    plt.show()
    plt.imshow(train_data.__getitem__(100)[0][2].numpy()[2])
    plt.show()
    plt.imshow(train_data.__getitem__(100)[0][3].numpy()[2])
    plt.show()
    val_data = DataReaderPlainImg(os.path.join(data_root, str(args.size), "val"), transform=val_transform)
    train_loader = torch.utils.data.DataLoader(train_data, batch_size=args.bs, shuffle=True, num_workers=2,
                                               pin_memory=True, drop_last=True, collate_fn=custom_collate)

    print(train_loader)
    val_loader = torch.utils.data.DataLoader(val_data, batch_size=1, shuffle=False, num_workers=2,
                                             pin_memory=True, drop_last=True, collate_fn=custom_collate)

    # TODO: loss function
    criterion = torch.nn.CrossEntropyLoss() # This criterion combines nn.LogSoftmax() and nn.NLLLoss() in one single class.
    ###########raise NotImplementedError("TODO: loss function")
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, momentum=0.9, weight_decay=1e-4)

    expdata = "  \n".join(["{} = {}".format(k, v) for k, v in vars(args).items()])
    logger.info(expdata)
    logger.info('train_data {}'.format(train_data.__len__()))
    logger.info('val_data {}'.format(val_data.__len__()))

    best_val_loss = np.inf
    # Train-validate for one epoch. You don't have to run it for 100 epochs, preferably until it starts overfitting.
    for epoch in range(10):
        print("Epoch {}".format(epoch))
        train(train_loader, model, criterion, optimizer)
        val_loss, val_acc = validate(val_loader, model, criterion)

        # save model
        if val_loss < best_val_loss:
            path_model = args.model_folder + '\checkpoint.pth'
            torch.save(model.state_dict(), path_model )
            ######raise NotImplementedError("TODO: save model if a new best validation error was reached")


# train one epoch over the whole training dataset. You can change the method's signature.
def train(loader, model, criterion, optimizer):
    model.train()
    for batch_i, (data, target) in enumerate(loader):
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        print('new batch ',batch_i, ' with loss: ', round(loss.item(),3))
        loss.backward()
        optimizer.step()

    ############raise NotImplementedError("TODO: training routine")


# validation function. you can change the method's signature.
def validate(loader, model, criterion):
    model.eval()
    for data,target in enumerate (loader):
        output = model(data)
        val_loss = criterion(output, target).mean()
        val_acc = accuracy(output, target)
    return val_loss, val_acc
    #########raise NotImplementedError("TODO: validation routine")
    # return mean_val_loss, mean_val_accuracy


if __name__ == '__main__':
    args = parse_arguments()
    pprint(vars(args))
    print()
    main(args)
