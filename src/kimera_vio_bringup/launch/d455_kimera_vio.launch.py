"""
RealSense D455 + Kimera-VIO launch.

This launch file starts:
1) realsense2_camera for IR + IMU streams
2) kimera_vio_ros node (package/executable configurable)
3) optional RViz2
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("kimera_vio_bringup")

    realsense_share = get_package_share_directory("realsense2_camera")
    realsense_launch = os.path.join(realsense_share, "launch", "rs_launch.py")

    default_params = os.path.join(pkg_share, "config", "kimera_d455_params.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "rviz_enable",
                default_value="false",
                description="Enable RViz2 visualization",
            ),
            DeclareLaunchArgument(
                "use_stereo",
                default_value="false",
                description="Enable stereo IR (infra1 + infra2)",
            ),
            DeclareLaunchArgument(
                "emitter_enabled",
                default_value="0",
                description="D455 IR projector: 0=off, 1=on",
            ),
            DeclareLaunchArgument(
                "enable_auto_exposure",
                default_value="false",
                description="Enable auto exposure for IR cameras",
            ),
            DeclareLaunchArgument(
                "infra_exposure",
                default_value="8500",
                description="Manual IR exposure (used if auto exposure is false)",
            ),
            DeclareLaunchArgument(
                "kimera_package",
                default_value="kimera_vio_ros",
                description="Kimera ROS2 package name",
            ),
            DeclareLaunchArgument(
                "kimera_executable",
                default_value="kimera_vio_ros_node",
                description="Kimera ROS2 executable name",
            ),
            DeclareLaunchArgument(
                "kimera_params_file",
                default_value=default_params,
                description="Kimera ROS2 parameter YAML path",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(realsense_launch),
                launch_arguments={
                    "enable_color": "false",
                    "enable_depth": "false",
                    "enable_infra1": "true",
                    "enable_infra2": LaunchConfiguration("use_stereo"),
                    "depth_module.infra_profile": "640,480,30",
                    "depth_module.emitter_enabled": LaunchConfiguration("emitter_enabled"),
                    "depth_module.enable_auto_exposure": LaunchConfiguration(
                        "enable_auto_exposure"
                    ),
                    "depth_module.exposure": LaunchConfiguration("infra_exposure"),
                    "enable_gyro": "true",
                    "enable_accel": "true",
                    "unite_imu_method": "2",
                    "enable_sync": "true",
                    "log_level": "info",
                }.items(),
            ),
            Node(
                package=LaunchConfiguration("kimera_package"),
                executable=LaunchConfiguration("kimera_executable"),
                name="kimera_vio_node",
                output="screen",
                emulate_tty=True,
                parameters=[LaunchConfiguration("kimera_params_file")],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                condition=IfCondition(LaunchConfiguration("rviz_enable")),
                arguments=["--ros-args", "--log-level", "warn"],
            ),
        ]
    )
