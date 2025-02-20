# from data_utils.ModelNetDataLoader import ModelNetDataLoader
# from data_utils.OFFDataLoader import *
import argparse
import numpy as np
import os
import torch
import logging
from tqdm import tqdm
from sklearn.metrics import confusion_matrix
import sys
import importlib
from path import Path
from data_utils.PCDLoader import *

import matplotlib.pyplot as plt
import seaborn as sn
import pandas as pd

# from tsnecuda import TSNE
from sklearn.manifold import TSNE
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = BASE_DIR
sys.path.append(os.path.join(ROOT_DIR, 'models'))


def parse_args():
    '''PARAMETERS'''
    parser = argparse.ArgumentParser('Testing')
    parser.add_argument('--use_cpu', action='store_true', default=False, help='use cpu mode')
    parser.add_argument('--gpu', type=str, default='0', help='specify gpu device')
    parser.add_argument('--batch_size', type=int, default=1, help='batch size in training')
    # parser.add_argument('--num_category', default=10, type=int, choices=[10, 40],  help='training on ModelNet10/40')
    parser.add_argument('--num_category', default=12, type=int, help='training on real dataset')
    parser.add_argument('--sample_point', type=bool, default=True,  help='Sampling on tacitle data')
    parser.add_argument('--num_point', type=int, default=50, help='Point Number')
    parser.add_argument('--log_dir', type=str, required=True, help='Experiment root')
    parser.add_argument('--use_normals', action='store_true', default=False, help='use normals')
    parser.add_argument('--use_uniform_sample', action='store_true', default=False, help='use uniform sampiling')
    parser.add_argument('--num_votes', type=int, default=3, help='Aggregate classification scores with voting')
    parser.add_argument('--SO3_Rotation', action='store_true', default=False, help='arbitrary rotation in SO3')
    return parser.parse_args()

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

activation = {}
def get_activation(name):
    def hook(model, input, output):
        # activation [name] = output[0].detach()
        activation [name] = output.detach()
    return hook



def test(model, loader, num_class=12, vote_num=1):
    mean_correct = []
    classifier = model.eval()
    class_acc = np.zeros((num_class, 3))
    print(len(loader))
    sample_num = len(loader)
    tSNE_X = np.zeros((sample_num, 256))
    tSNE_Y = np.zeros((sample_num, 1))
    y_pred = []
    y_true = []

    num_correct = 0
    num_samples = 0
    all_pred_new = []
    all_true_new = []
    # classes = list(find_classes(data_path).keys())
    # print(classes)

    for j, data in tqdm(enumerate(loader), total=len(loader)):
        if not args.use_cpu:
            # points, target = points.cuda(), target.cuda()
            points, target = data['pointcloud'].to(device).float(), data['category'].to(device)


        points = points.transpose(2, 1)
        vote_pool = torch.zeros(target.size()[0], num_class).cuda()

        ###################################################################################
        output_new, _ = classifier(points)
        _, preds_new = torch.max(output_new.data, 1)
        # print(preds_new)
        y_true_new = target.data.cpu().numpy()
        y_pred_new = preds_new.data.cpu().numpy()

        all_pred_new += list(y_pred_new)
        all_true_new += list(y_true_new)

        num_correct += (y_pred_new == y_true_new).sum()
        num_samples += y_pred_new.size


        # Output for fc2 feature
        classifier.fc2.register_forward_hook(get_activation('fc2'))
        output_tSNE = classifier(points)
        feature_tSNE = activation['fc2']
        feature_tSNE_np = feature_tSNE.data.cpu().numpy()
        # print(".....................")
        # print(feature_tSNE_np.shape)
        tSNE_X[j] = feature_tSNE_np[0]
        tSNE_Y[j] = int(y_true_new)
        # print(feature_tSNE_np)


    print(tSNE_X.shape)
    print(tSNE_Y.shape)
    X_embedded = TSNE(perplexity=30, learning_rate=10.0).fit_transform(tSNE_X)
    print(X_embedded.shape)
    classes_name = ['cleaner', 'coffee', 'cup', 'eraser', 'glasses_box', 'jam', 'olive_oil',
                    'shampoo', 'spray', 'sugar', 'tape', 'wine']
    # Changing the value of perplexity HERE (5-50):
    # print(tSNE_Y[:,0])
    df = pd.DataFrame()
    df['y'] = tSNE_Y[:,0]
    df['comp-1'] = X_embedded[:,0]
    df['comp-2'] = X_embedded[:,1]
    list_y = df.y.tolist()
    # print(list_y)
    # print(type(list_y[0]))

    for i, item in enumerate(list_y):
        list_y[i] = classes_name[int(item)]

    print(list_y)

    # sn.set(font_scale = 1.3, style="white")
    # sn.set_theme(style="white")
    plt.figure(figsize = (12,7))
    sn.scatterplot(x='comp-1', y='comp-2', hue=list_y,
                   # palette=sn.color_palette("flare", as_cmap=True),
                   # palette=sn.color_palette("Spectral", as_cmap=True),
                   palette = sn.color_palette("Paired"),
                   data=df).set(xlabel='Component-1', ylabel='Component-2')

    plt.savefig('/home/prajval/Desktop/tSNE_plot_new/'
                +'tSNE_tactile_' + str(datetime.now()) + '.png')
    print("Saved the tSNE plot on Desktop")



    cf_matrix_new = confusion_matrix(all_true_new, all_pred_new, normalize='true')

    return 0.0, 0.0, cf_matrix_new


def main(args):
    def log_string(str):
        logger.info(str)
        print(str)

    '''HYPER PARAMETER'''
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

    '''CREATE DIR'''
    experiment_dir = 'log/classification/' + args.log_dir

    '''LOG'''
    args = parse_args()
    logger = logging.getLogger("Model")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler('%s/eval.txt' % experiment_dir)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    log_string('PARAMETER ...')
    log_string(args)

    '''DATA LOADING'''
    log_string('Load dataset ...')
    # tactile_data_path = 'data/tactile_data_pcd/'
    tactile_data_path = 'data/tactile_pcd_10_sampled_21.02/'
    visual_data_path = 'data/visual_data_pcd/'
    # tactile_data_path = 'data/visual_data_pcd/'
    # data_path = 'data/modelnet40_normal_resampled/'
    # data_path = Path("mesh_data/ModelNet10")


    test_dataset = PCDPointCloudData(tactile_data_path,
                                     folder='Test',
                                     sample_method='Voxel',
                                     num_point=args.num_point,
                                     sample=args.sample_point,
                                     est_normal=args.use_normals,
                                     rotation=False)
    testDataLoader = torch.utils.data.DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False, num_workers=10)

    '''MODEL LOADING'''
    num_class = args.num_category
    model_name = os.listdir(experiment_dir + '/logs')[0].split('.')[0]
    model = importlib.import_module(model_name)

    classifier = model.get_model(num_class, normal_channel=args.use_normals)
    if not args.use_cpu:
        classifier = classifier.cuda()

    checkpoint = torch.load(str(experiment_dir) + '/checkpoints/best_model.pth')
    classifier.load_state_dict(checkpoint['model_state_dict'])

    # Load labels:
    classes = find_classes(tactile_data_path)
    print(classes)
    print(classes.keys)




    with torch.no_grad():
        instance_acc, class_acc, cf_matrix_new = test(classifier.eval(), testDataLoader, vote_num=args.num_votes, num_class=num_class)
        log_string('Test Instance Accuracy: %f, Class Accuracy: %f' % (instance_acc, class_acc))

        # Draw confusion matrix
        df_cm = pd.DataFrame(cf_matrix_new,
                             index = [i for i in classes.keys()],
                             columns = [i for i in classes.keys()])
        plt.figure(figsize = (12,7))
        sn.heatmap(df_cm, annot=True)
        # plt.savefig(experiment_dir + '/' + str(datetime.now()) + '.png')

        # df_cm = pd.DataFrame(cf_matrix_new/np.sum(cf_matrix_old) *10,
        #                      index = [i for i in classes.keys()], columns = [i for i in classes.keys()])
        # plt.figure(figsize = (12,7))
        # sn.heatmap(df_cm, annot=True)
        # plt.savefig(experiment_dir + '/' + str(datetime.now()) + '.png')

if __name__ == '__main__':
    args = parse_args()
    main(args)
