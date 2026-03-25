import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'controller_reader'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=['setuptools', 'pyserial'],
    zip_safe=True,
    maintainer='linkerbot',
    maintainer_email='helloworld@linkerbot.cn',
    description='USB串口控制器数据读取节点，读取6轴控制器角度数据并发布ROS2话题',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'controller_reader_node = controller_reader.controller_reader_node:main'
        ],
    },
)
