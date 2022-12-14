import argparse
import pathlib
import importlib
from conf import default, general, paths
from ops.dataloader import get_train_val_dataset, data_augmentation, prep_data, PredictDataGen_opt
import tensorflow as tf
import os
import time
from multiprocessing import Process
import sys
import numpy as np
from tqdm import tqdm

parser = argparse.ArgumentParser(
    description='Predict NUMBER_MODELS models based in the same parameters'
)

parser.add_argument( # Experiment number
    '-e', '--experiment',
    type = int,
    default = 1,
    help = 'The number of the experiment'
)

parser.add_argument( # batch size
    '-b', '--batch-size',
    type = int,
    default = default.BATCH_SIZE,
    help = 'The number of samples of each batch'
)

parser.add_argument( # Number of models to be trained
    '-n', '--number-models',
    type = int,
    default = default.N_TRAIN_MODELS,
    help = 'The number models to be trained from the scratch'
)

parser.add_argument( # Experiment path
    '-x', '--experiments-path',
    type = pathlib.Path,
    default = paths.EXPERIMENTS_PATH,
    help = 'The patch to data generated by all experiments'
)

args = parser.parse_args()

exp_path = os.path.join(str(args.experiments_path), f'exp_{args.experiment}')
if not os.path.exists(exp_path):
    os.mkdir(exp_path)

logs_path = os.path.join(exp_path, f'logs')
models_path = os.path.join(exp_path, f'models')
visual_path = os.path.join(exp_path, f'visual')
predicted_path = os.path.join(exp_path, f'predicted')
results_path = os.path.join(exp_path, f'results')

def run(model_idx):
    outfile = os.path.join(logs_path, f'pred_{args.experiment}_{model_idx}.txt')
    with open(outfile, 'w') as sys.stdout:

        test_dataset = PredictDataGen_opt(general.YEAR_2, args.batch_size)
        ds_train, ds_val, n_patches_train, n_patches_val = get_train_val_dataset(general.YEAR_2)

        AUTOTUNE = tf.data.experimental.AUTOTUNE
        ds_train = ds_train.map(data_augmentation, num_parallel_calls=AUTOTUNE)
        ds_train = ds_train.map(prep_data, num_parallel_calls=AUTOTUNE)
        ds_train = ds_train.batch(args.batch_size)
        ds_train = ds_train.prefetch(AUTOTUNE)

        ds_val = ds_val.map(data_augmentation, num_parallel_calls=AUTOTUNE)
        ds_val = ds_val.map(prep_data, num_parallel_calls=AUTOTUNE)
        ds_val = ds_val.batch(args.batch_size)
        ds_val = ds_val.prefetch(AUTOTUNE)

        train_steps = (n_patches_train // args.batch_size)
        val_steps = (n_patches_val // args.batch_size)

        blocks_shape = test_dataset.blocks_shape
        img_shape = test_dataset.shape

        model_m =importlib.import_module(f'conf.model_{args.experiment}')
        model = model_m.get_model()

        print('Loss: ', model.loss)
        print('Weights: ',model.loss.weights)
        print('Optimizer: ', model.optimizer)

        model.load_weights(os.path.join(models_path, f'model_{model_idx}'))

        model.evaluate(ds_train, verbose = 2, steps = train_steps)
        model.evaluate(ds_val, verbose = 2, steps = val_steps)

        pred = []
        t0 = time.perf_counter()
        for test_batch in test_dataset:
            pred_batch = model.predict_on_batch(test_batch)
            pred.append(pred_batch)

        print(f'Prediction time: {time.perf_counter() - t0} s')

        patch_size = general.PATCH_SIZE
        n_classes = general.N_CLASSES
        test_crop = general.TEST_CROP

        pred = np.concatenate(pred, axis=0).reshape(blocks_shape+(patch_size, patch_size, n_classes))[: ,: ,test_crop:-test_crop ,test_crop:-test_crop, :]

        pred_reconstructed = None
        for line_i in pred:
            if pred_reconstructed is None:
                pred_reconstructed = np.column_stack(line_i)
            else:
                pred_reconstructed = np.row_stack((pred_reconstructed, np.column_stack(line_i)))

        pred_reconstructed = pred_reconstructed[:img_shape[0], :img_shape[1], :]
        #preds_l.append(pred_reconstructed.astype(np.float16))
        np.save(os.path.join(predicted_path, f'pred_{model_idx}.npy'), pred_reconstructed.astype(np.float16))


if __name__=="__main__":
    
    for model_idx in range(args.number_models):
        p = Process(target=run, args=(model_idx,))
        p.start()
        p.join()
    
    preds = []
    for model_idx in tqdm(range(args.number_models), desc = 'Opening prediction files'):
        preds.append(np.load(os.path.join(predicted_path, f'pred_{model_idx}.npy')))
    preds = np.array(preds)
    np.save(os.path.join(predicted_path, 'pred_m') ,preds.mean(axis=0))