import argparse
import os

import matplotlib
try:
    matplotlib.use('Agg')
except Exception:
    raise

import chainer
from chainer.serializers import npz
from chainer import training
from chainer.training import extensions

from dataset import CelebADataset
from net import Encoder
from net import Generator
from updater import EncUpdater


def main():
    parser = argparse.ArgumentParser(description='Train Encoder')
    parser.add_argument('--batchsize', '-b', type=int, default=64,
                        help='Number of images in each mini-batch')
    parser.add_argument('--epoch', '-e', type=int, default=100,
                        help='Number of sweeps over the dataset to train')
    parser.add_argument('--gpu', '-g', type=int, default=-1,
                        help='GPU ID (negative value indicates CPU)')
    parser.add_argument('--dataset', '-i', default='data/celebA/',
                        help='Directory of image files.')
    parser.add_argument('--out', '-o', default='result',
                        help='Directory to output the result')
    parser.add_argument('--resume', '-r', default='',
                        help='Resume the training from snapshot')
    parser.add_argument('--snapshot_interval', type=int, default=10000,
                        help='Interval of snapshot')
    parser.add_argument('--display_interval', type=int, default=1000,
                        help='Interval of displaying log to console')
    parser.add_argument('--gen', default='gen.npz')
    parser.add_argument('--enc', default=None)
    args = parser.parse_args()

    print('GPU: {}'.format(args.gpu))
    print('# batchsize: {}'.format(args.batchsize))
    print('# epoch: {}'.format(args.epoch))
    print('')

    # Set up a neural network to train
    gen = Generator()
    npz.load_npz(args.gen, gen)
    enc = Encoder()
    if args.enc is not None:
        npz.load_npz(args.enc, enc)

    if args.gpu >= 0:
        chainer.cuda.get_device_from_id(args.gpu).use()
        gen.to_gpu()
        enc.to_gpu()

    # Setup an optimizer
    def make_optimizer(model, alpha=0.0005, beta1=0.9):
        optimizer = chainer.optimizers.Adam(alpha=alpha, beta1=beta1)
        optimizer.setup(model)
        optimizer.add_hook(chainer.optimizer.WeightDecay(0.0001), 'hook_dec')
        return optimizer
    opt_gen = make_optimizer(gen)
    gen.disable_update()
    opt_enc = make_optimizer(enc)

    # Setup a dataset
    all_files = os.listdir(args.dataset)
    image_files = [f for f in all_files if ('png' in f or 'jpg' in f)]
    print('{} contains {} image files'.format(args.dataset, len(image_files)))
    train = CelebADataset(paths=image_files, root=args.dataset)

    train_iter = chainer.iterators.SerialIterator(train, args.batchsize)

    # Set up a trainer
    updater = EncUpdater(
        models=(gen, enc),
        iterator=train_iter,
        optimizer={'gen': opt_gen, 'enc': opt_enc},
        device=args.gpu)
    trainer = training.Trainer(updater, (args.epoch, 'epoch'), out=args.out)

    snapshot_interval = (args.snapshot_interval, 'iteration')
    display_interval = (args.display_interval, 'iteration')
    trainer.extend(
        extensions.snapshot(filename='snapshot_enc_iter_{.updater.iteration}.npz'),
        trigger=snapshot_interval)
    trainer.extend(extensions.ExponentialShift(
        'alpha', 0.5, optimizer=opt_enc), trigger=(10, 'epoch'))
    trainer.extend(extensions.snapshot_object(
        enc, 'enc_iter_{.updater.iteration}.npz'), trigger=snapshot_interval)
    trainer.extend(extensions.LogReport(trigger=display_interval, log_name='train_enc.log'))
    trainer.extend(extensions.PrintReport([
        'epoch', 'iteration', 'enc/loss',
    ]), trigger=display_interval)
    trainer.extend(extensions.PlotReport(
        ['enc/loss'], trigger=display_interval, file_name='enc-loss.png'))
    trainer.extend(extensions.ProgressBar(update_interval=10))

    if args.resume:
        chainer.serializers.load_npz(args.resume, trainer)

    # Run the training
    trainer.run()


if __name__ == '__main__':
    main()
