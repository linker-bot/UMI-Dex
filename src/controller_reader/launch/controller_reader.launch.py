#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@file    controller_reader.launch.py
@brief   控制器数据读取节点 launch 文件

@details 启动 controller_reader_node，可通过命令行参数或YAML配置文件覆盖默认参数。
         用法:
           ros2 launch controller_reader controller_reader.launch.py
           ros2 launch controller_reader controller_reader.launch.py serial_port:=/dev/ttyUSB1
           ros2 launch controller_reader controller_reader.launch.py params_file:=/path/to/params.yaml
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    """
    @brief 生成 launch 描述

    @return LaunchDescription 对象
    """
    pkg_share = get_package_share_directory('controller_reader')
    default_params_file = os.path.join(pkg_share, 'config', 'controller_reader_params.yaml')

    # -------------------- 声明 launch 参数 --------------------
    declare_params_file = DeclareLaunchArgument(
        'params_file',
        default_value=default_params_file,
        description='YAML参数配置文件的完整路径'
    )

    declare_serial_port = DeclareLaunchArgument(
        'serial_port',
        default_value='',
        description='串口端口号（覆盖YAML配置，留空则使用YAML配置）'
    )

    declare_serial_baudrate = DeclareLaunchArgument(
        'serial_baudrate',
        default_value='',
        description='串口波特率（覆盖YAML配置，留空则使用YAML配置）'
    )

    # -------------------- 节点定义（使用YAML配置文件） --------------------
    controller_reader_node = Node(
        package='controller_reader',
        executable='controller_reader_node',
        name='controller_reader_node',
        output='screen',
        emulate_tty=True,
        parameters=[LaunchConfiguration('params_file')],
    )

    return LaunchDescription([
        declare_params_file,
        declare_serial_port,
        declare_serial_baudrate,
        controller_reader_node,
    ])
