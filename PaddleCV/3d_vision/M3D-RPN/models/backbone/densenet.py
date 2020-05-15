from __future__ import division
from __future__ import print_function

import paddle.fluid as fluid

import paddle.fluid.dygraph.nn as nn
from paddle.fluid.dygraph.container import Sequential

from hapi.model import Model


def _bn_function_factory(norm, conv):
    def bn_function(*inputs):
        concated_features = fluid.layers.concat(inputs, 1)
        bottleneck_output = conv(norm(concated_features))
        return bottleneck_output

    return bn_function


class _DenseLayer(fluid.dygraph.Layer):
    def __init__(self, num_input_features, growth_rate, bn_size, drop_rate, memory_efficient=False):
        super(_DenseLayer, self).__init__()
        self.add_sublayer('norm1', nn.BatchNorm(num_input_features, act='relu'))
        self.add_sublayer('conv1', nn.Conv2D(num_input_features, bn_size * growth_rate,
                                             filter_size=1, stride=1, bias_attr=False))
        self.add_sublayer('norm2', nn.BatchNorm(bn_size * growth_rate, act='relu'))
        self.add_sublayer('conv2', nn.Conv2D(bn_size * growth_rate, growth_rate,
                                             filter_size=3, stride=1, padding=1, bias_attr=False))
        self.drop_rate = float(drop_rate)
        self.memory_efficient = memory_efficient

    def forward(self, *prev_features):
        bn_function = _bn_function_factory(self.norm1, self.conv1)
        bottleneck_output = bn_function(*prev_features)
        new_features = self.conv2(self.norm2(bottleneck_output))
        if self.drop_rate > 0:
            new_features = fluid.layers.dropout(new_features, self.drop_rate)
        return new_features


class _DenseBlock(fluid.dygraph.Layer):
    def __init__(self, num_layers, num_input_features, bn_size, growth_rate, drop_rate, memory_efficient=False):
        super(_DenseBlock, self).__init__()
        for i in range(num_layers):
            layer = _DenseLayer(
                num_input_features + i * growth_rate,
                growth_rate=growth_rate,
                bn_size=bn_size,
                drop_rate=drop_rate,
                memory_efficient=memory_efficient,
            )
            self.add_sublayer('denselayers%d' % (i + 1), layer)

    def forward(self, init_features):
        features = [init_features]
        for name, layer in self.items():
            new_features = layer(*features)
            features.append(new_features)
        return fluid.layers.concat(features, axis=1)


class _Transition(Sequential):
    def __init__(self, num_input_features, num_output_features):
        super(_Transition, self).__init__()
        self.add_sublayer('norm', nn.BatchNorm(num_input_features, act='relu'))
        self.add_sublayer('conv', nn.Conv2D(num_input_features, num_output_features, filter_size=1, stride=1, bias_attr=False))
        self.add_sublayer('pool', nn.Pool2d(pool_size=2, pool_stride=2, pool_type='avg'))


class DenseNet(Model):
    """

    """

    def __init__(self, growth_rate=32, block_config=(6, 12, 24, 16),
                 num_init_features=64, bn_size=4, drop_rate=0, num_classes=1000, memory_efficient=False):
        super(DenseNet, self).__init__()

        self.features = Sequential(
            ('conv0', nn.Conv2D(3, num_init_features, filter_size=7, stride=2, padding=3, bias_attr=False)),
            ('norm0', nn.BatchNorm(num_init_features, act='relu')),
            ('pool0', nn.Pool2d(pool_size=3, pool_stride=2, pool_padding=1, pool_type='max'))
        )

        # Each denseblock
        num_features = num_init_features
        for i, num_layers in enumerate(block_config):
            block = _DenseBlock(
                num_layers=num_layers,
                num_input_features=num_features,
                bn_size=bn_size,
                growth_rate=growth_rate,
                drop_rate=drop_rate,
                memory_efficient=memory_efficient
            )

            self.features.add_sublayer('denseblock%d' % (i + 1), Sequential(block))
            num_features = num_features + num_layers * growth_rate
            if i != len(block_config) - 1:
                trans = _Transition(num_input_features=num_features,
                                    num_output_features=num_features // 2)
                self.features.add_sublayer('transition%d' % (i + 1), trans)
                num_features = num_features // 2

        # Final batch norm
        self.features.add_sublayer('norm5', nn.BatchNorm(num_features))

        # Linear layer
        self.classifier = nn.Linear(num_features, num_classes)

        # init

    def forward(self, x):
        features = self.features(x)
        out = fluid.layers.relu(features)
        out = fluid.layers.adaptive_pool2d(
                  input=out,
                  pool_size=[1, 1],
                  pool_type='avg')
        out = fluid.layers.flatten(out, 1)
        out = self.classifier(out)
        return out


def _densenet(arch, growth_rate, block_config, num_init_features,  **kwargs):
    model = DenseNet(growth_rate, block_config, num_init_features, **kwargs)
    return model


def densenet121(**kwargs):
    return _densenet('densenet121', 32, (6, 12, 24, 16), 64, **kwargs)


def densenet161(**kwargs):
    return _densenet('densenet161', 48, (6, 12, 36, 24), 96, **kwargs)


def densenet169(**kwargs):
    return _densenet('densenet169', 32, (6, 12, 32, 32), 64, **kwargs)


def densenet201(**kwargs):
    return _densenet('densenet201', 32, (6, 12, 48, 32), 64, **kwargs)





