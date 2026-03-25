#!/usr/bin/env python3
"""
@file ros_topic_capture_save.py
@brief 订阅 ROS2 话题并保存为 CSV 文件，不涉及相机采集

@details
  订阅 VIO 位姿与控制器角度话题，将接收到的数据实时写入 CSV 文件：
  - /poseimu  (geometry_msgs/PoseWithCovarianceStamped) -> pose_imu.csv
  - /controller/angles (std_msgs/Float32MultiArray)     -> controller_angles.csv

  时间戳说明：
  - pose_imu.csv 使用 VIO 消息自带的 header.stamp（传感器/算法时间戳）。
  - controller_angles.csv 使用节点本地时钟 (node.get_clock().now())，因为
    Float32MultiArray 不携带标准消息头，编码器固件也不提供同步时间戳。
    如需更严格的时间对齐，可在发布端改用带 Header 的自定义消息。

  用法：
  python3 ros_topic_capture_save.py -o my_data -t 60
"""

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ROS2 依赖
try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from std_msgs.msg import Float32MultiArray
    HAS_ROS2 = True
except ImportError as e:
    HAS_ROS2 = False
    _ROS2_IMPORT_ERROR = str(e)


def pose_csv_header():
    """
    @brief 返回 pose_imu.csv 表头
    @return CSV 表头字符串
    """
    return (
        "timestamp_sec,timestamp_nsec,"
        "pos_x,pos_y,pos_z,"
        "orient_x,orient_y,orient_z,orient_w\n"
    )


def controller_angles_csv_header():
    """
    @brief 返回 controller_angles.csv 表头
    @return CSV 表头字符串
    """
    return (
        "timestamp_sec,timestamp_nsec,"
        "angle_0,angle_1,angle_2,angle_3,angle_4,angle_5\n"
    )


if HAS_ROS2:
    class RosDataSubscriber(Node):
        """
        @brief 订阅 /poseimu、/controller/angles 并写入 CSV 的 ROS2 节点
        """

        def __init__(self, pose_csv_path, ctrl_csv_path, csv_lock, subscribe_pose, subscribe_ctrl):
            super().__init__("ros_topic_capture_node")
            self.pose_csv_path = pose_csv_path
            self.ctrl_csv_path = ctrl_csv_path
            self.csv_lock = csv_lock
            self.pose_count = 0
            self.ctrl_count = 0

            # BEST_EFFORT 与传感器/VIO 发布端 QoS 匹配；
            # 使用 RELIABLE 会因 QoS 不兼容导致收不到数据。
            qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=10
            )
            if subscribe_pose:
                self.sub_pose = self.create_subscription(
                    PoseWithCovarianceStamped,
                    "/poseimu",
                    self.pose_callback,
                    qos
                )
                self.get_logger().info("已订阅 /poseimu")
            if subscribe_ctrl:
                self.sub_ctrl = self.create_subscription(
                    Float32MultiArray,
                    "/controller/angles",
                    self.ctrl_callback,
                    qos
                )
                self.get_logger().info("已订阅 /controller/angles")

        def pose_callback(self, msg):
            """
            @brief /poseimu 话题回调函数，使用消息自带的 header.stamp 作为时间戳
            @param msg 接收到的 PoseWithCovarianceStamped 消息
            """
            with self.csv_lock:
                with open(self.pose_csv_path, "a") as f:
                    p = msg.pose.pose.position
                    q = msg.pose.pose.orientation
                    f.write(
                        f"{msg.header.stamp.sec},{msg.header.stamp.nanosec},"
                        f"{p.x},{p.y},{p.z},"
                        f"{q.x},{q.y},{q.z},{q.w}\n"
                    )
            self.pose_count += 1

        def ctrl_callback(self, msg):
            """
            @brief /controller/angles 话题回调函数，使用节点本地时钟作为时间戳
            @param msg 接收到的 Float32MultiArray 消息（无标准 Header）
            """
            # Float32MultiArray 不含 header.stamp，用节点时钟补充接收时刻
            stamp = self.get_clock().now()
            sec = stamp.nanoseconds // 1_000_000_000
            nsec = stamp.nanoseconds % 1_000_000_000
            with self.csv_lock:
                with open(self.ctrl_csv_path, "a") as f:
                    angles = ",".join(str(v) for v in msg.data)
                    f.write(f"{sec},{nsec},{angles}\n")
            self.ctrl_count += 1


def main():
    # -------------------- 1. 参数解析 --------------------
    parser = argparse.ArgumentParser(
        description="ROS2 话题采集并保存为 CSV（/poseimu, /controller/angles）"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="输出目录（默认: output_topics_YYYYMMDD_HHMMSS）"
    )
    parser.add_argument(
        "-t", "--duration",
        type=float,
        default=0,
        help="录制时长（秒），0 表示按 Ctrl+C 手动停止"
    )
    parser.add_argument(
        "--no-pose",
        action="store_true",
        help="不订阅 /poseimu"
    )
    parser.add_argument(
        "--no-controller",
        action="store_true",
        help="不订阅 /controller/angles"
    )
    args = parser.parse_args()

    # -------------------- 2. 环境检查 --------------------
    if not HAS_ROS2:
        print("错误: 未检测到 ROS2 (rclpy) 依赖", file=sys.stderr)
        err = getattr(sys.modules[__name__], "_ROS2_IMPORT_ERROR", "未知错误")
        print(f"导入错误: {err}", file=sys.stderr)
        print("请确保已 source ROS2 环境，例如: source /opt/ros/jazzy/setup.bash", file=sys.stderr)
        sys.exit(1)

    # -------------------- 3. 创建输出目录 --------------------
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(f"output_topics_{timestamp}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {output_dir}")

    # -------------------- 4. 初始化节点与 CSV --------------------
    pose_csv_path = output_dir / "pose_imu.csv"
    ctrl_csv_path = output_dir / "controller_angles.csv"
    csv_lock = threading.Lock()
    
    subscribe_pose = not args.no_pose
    subscribe_ctrl = not args.no_controller

    if not (subscribe_pose or subscribe_ctrl):
        print("未指定任何需要订阅的话题。程序退出。")
        sys.exit(0)

    rclpy.init()
    ros_node = RosDataSubscriber(
        pose_csv_path, ctrl_csv_path, csv_lock, subscribe_pose, subscribe_ctrl
    )

    # 写入 CSV 表头
    if subscribe_pose:
        with open(pose_csv_path, "w") as f:
            f.write(pose_csv_header())
    if subscribe_ctrl:
        with open(ctrl_csv_path, "w") as f:
            f.write(controller_angles_csv_header())

    # -------------------- 5. Spin 循环（录制） --------------------
    print("按 Ctrl+C 停止录制")
    if args.duration > 0:
        print(f"录制时长: {args.duration} 秒")

    start_time = time.time()
    try:
        while rclpy.ok():
            if args.duration > 0 and (time.time() - start_time) >= args.duration:
                print(f"\n录制时间到 ({args.duration} 秒)")
                break
            
            # 使用 spin_once 以便我们可以检查 duration 并响应 KeyboardInterrupt
            rclpy.spin_once(ros_node, timeout_sec=0.1)

    except KeyboardInterrupt:
        print("\n用户中断，停止录制")
    except ExternalShutdownException:
        pass
    finally:
        try:
            ros_node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass

    # -------------------- 6. 统计与清理 --------------------
    print(f"录制结束。")
    if subscribe_pose:
        print(f"  pose_imu 消息数: {ros_node.pose_count}")
    if subscribe_ctrl:
        print(f"  controller_angles 消息数: {ros_node.ctrl_count}")


if __name__ == "__main__":
    main()
