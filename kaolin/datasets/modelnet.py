# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Callable, Iterable, Optional, Union

import torch
import sys
from pathlib import Path
import scipy.io as sio
import numpy as np

import kaolin as kal


_MODELNET10_CLASSES = ['bathtub', 'bed', 'chair', 'desk', 'dresser', 'monitor',
                       'night_stand', 'sofa', 'table', 'toilet']


class ModelNet(torch.utils.data.Dataset):
    r"""Dataset class for the ModelNet10/40 datasets.

    Args:
        basedir (str): Path to the base directory of the ModelNet dataset.
        rep (str, optional): Type of representation to convert the dataset into
            (default: 'mesh').
        split (str, optional): Split to load ('train' vs 'test',
            default: 'train').
        categories (iterable, optional): List of categories to load
            (default: ['chair']).
        device (str or torch.device, optional): Device to use (cpu,
            cuda-capable device, etc.).
        transform (callable, optional): A function/transform to apply on each
            loaded example.

    **kwargs
        num_points (int, optional): Number of points in the returned pointcloud
            (if using pointcloud representation, default: 1024).

    """

    def __init__(self, basedir: Union[str, Path], rep: Optional[str] = 'mesh',
                 split: Optional[str] = 'train',
                 categories: Optional[Iterable] = None,
                 device: Optional[Union[torch.device, str]] = 'cpu',
                 transform: Optional[Callable] = None,
                 **kwargs):

        super(ModelNet, self).__init__()

        if rep not in ['mesh', 'pointcloud']:
            raise ValueError('Argument \'rep\' must be one of \'mesh\' '
                ' or \'pointcloud\'. Got {0} instead.'.format(rep))
        if split not in ['train', 'test']:
            raise ValueError('Argument \'split\' must be one of \'train\' '
                ' or \'test\'. Got {0} instead.'.format(split))

        if not isinstance(basedir, Path):
            basedir = Path(basedir)

        # Find categories provided by the dataset
        avail_categories = [d.name for d in basedir.iterdir() if d.is_dir()]
        self.categories = categories or avail_categories
        self.paths = []
        self.labels = []
        for idx, cat in enumerate(self.categories):
            if cat not in avail_categories:
                raise ValueError('Invalid ModelNet class {0}. Valid classes '
                    ' are {1}'.format(cat, avail_categories))
            catdir = basedir / cat / split
            for path in catdir.glob('*.off'):
                self.paths.append(path)
                self.labels.append(idx)

        self.rep = rep
        self.device = device
        self.transform = transform
        self.num_points = kwargs.get('num_points', 1024)

    def __len__(self):
        r"""Returns the length of the dataset. """
        return len(self.paths)

    def __getitem__(self, idx):
        r"""Returns the item at index `idx`. """

        mesh = kal.rep.TriangleMesh.from_off(self.paths[idx])
        mesh.to(self.device)
        label = torch.LongTensor([self.labels[idx]]).to(self.device)
        if self.rep == 'mesh':
            if self.transform is not None:
                mesh = self.transform(mesh)
            return mesh, label
        elif self.rep == 'pointcloud':
            pts, _ = mesh.sample(self.num_points)
            if self.transform is not None:
                pts = self.transform(pts)
            return pts, label
        else:
            raise NotImplementedError


class ModelNetPointCloud(torch.utils.data.Dataset):
    def __init__(self, basedir: Union[str, Path],
                 split: Optional[str] = 'train',
                 categories: Optional[Iterable] = None,
                 device: Optional[Union[torch.device, str]] = 'cpu',
                 transform: Optional[Callable] = None,
                 num_points: int = 2**10,
                 sample_points: int = 2**12):
        super(ModelNetPointCloud, self).__init__()

        if split not in ['train', 'test']:
            raise ValueError('Argument \'split\' must be one of \'train\' '
                ' or \'test\'. Got {0} instead.'.format(split))

        if not isinstance(basedir, Path):
            basedir = Path(basedir)

        # Find categories provided by the dataset
        avail_categories = [d.name for d in basedir.iterdir() if d.is_dir()]
        self.categories = categories or avail_categories
        self.paths = []
        self.labels = []
        for idx, cat in enumerate(self.categories):
            if cat not in avail_categories:
                raise ValueError('Invalid ModelNet class {0}. Valid classes '
                    ' are {1}'.format(cat, avail_categories))
            catdir = basedir / cat / split
            for path in catdir.glob('*.off'):
                self.paths.append(path)
                self.labels.append(idx)

        self.device = device
        self.transform = transform
        self.num_points = num_points
        self.sample_points = sample_points
        self.sample_cache = dict()

    def __len__(self):
        r"""Returns the length of the dataset. """
        return len(self.paths)

    def __getitem__(self, idx):
        r"""Returns the item at index `idx`. """
        try:
            if idx not in self.sample_cache:
                mesh = kal.rep.TriangleMesh.from_off(self.paths[idx])
                full_pts, _ = mesh.sample(self.sample_points)
                self.sample_cache[idx] = full_pts
            else:
                full_pts = self.sample_cache[idx]

            # Downsample points
            idxs = np.random.choice(full_pts.size(0), size=self.num_points,
                                    replace=False)
            pts = full_pts[idxs, :]
            pts = pts.to(self.device)
            if self.transform is not None:
                pts = self.transform(pts)
        except:
            import pdb; pdb.set_trace()
        return pts


class ModelNetVoxels(object):
    r""" Dataloader for downloading and reading from ModelNet.


    Args:
        root (str): location the dataset should be downloaded to /loaded from
        train (bool): if True loads training set, else loads test
        download (bool): downloads the dataset if not found in root
        categories (str): list of object classes to be loaded
        single_view (bool): if true only one roation is used, if not all 12 views are loaded

    Returns:
        .. code-block::

        dict: {
            'attributes': {'name': str, 'class': str},
            'data': {'voxels': torch.Tensor}
        }


    Examples:
        >>> dataset = ModelNet(root='../data/')
        >>> train_loader = DataLoader(dataset, batch_size=10, shuffle=True, num_workers=8)
        >>> obj = next(iter(train_loader))
        >>> obj['data']['data']
        torch.Size([10, 30, 30, 30])
    """

    def __init__(self, root: str = '../data/', train: bool = True, test: bool = True,
                 download: bool = True, categories: list = ['chair'], single_view: bool = True):
        if not os.path.exists(root + '/ModelNet/'):
            assert download, "ModelNet is not found, and download is set to False"
            assert (train or test), 'either train or test must be set to True'

        if not single_view:
            side = ''
        else:
            side = '_1'

        all_classes = [os.path.basename(os.path.dirname(c))
                       for c in glob(root + '/ModelNet/volumetric_data/*/')]
        self.names = []
        for category in categories:
            assert category in all_classes, 'object class {0} not in list of availible classes: {1}'.format(
                category, all_classes)
            if train:
                self.names += glob(
                    root + '/ModelNet/volumetric_data/{0}/*/{1}/*{2}.mat'.format(category, 'train', side))
            if test:
                self.names += glob(
                    root + '/ModelNet/volumetric_data/{0}/*/{1}/*{2}.mat'.format(category, 'test', side))

    def __len__(self):
        return len(self.names)

    def __getitem__(self, item):
        object_path = self.names[item]

        # convert the path to the linux like path in o
        if sys.platform.startswith('win'):
            object_path = object_path.replace('\\', '/')


        object_class = object_path.split('/')[-4]
        object_name = object_path.split('/')[-1]
        object_data = sio.loadmat(object_path)['instance']
        # object_shape = object_data.shape

        data = dict()
        attributes = dict()
        attributes['name'] = object_name
        attributes['class'] = object_class
        data['voxels'] = torch.FloatTensor(object_data.astype(float))

        return {'attributes': attributes, 'data': data}
