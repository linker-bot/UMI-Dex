#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@file    controller_reader_node.py
@brief   USB串口控制器数据读取ROS2节点

@details 通过USB串口读取6轴控制器的角度数据，
         支持低通滤波，将滤波角度映射为控制值（0-1023）后发布到ROS2话题。
         话题:
           - controller/angles      (std_msgs/Float32MultiArray)  映射后的6轴控制值（0-1023）
           - controller/angles_raw  (std_msgs/Float32MultiArray)  原始6轴角度
@date    2026-02-11
"""

import array
import serial
import struct
import threading
from typing import List, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, MultiArrayDimension


# ==================== 数据包配置 ====================
PACKET_SIZE = 28                  # 数据包大小：6*4字节float + 4字节帧尾
FRAME_TAIL = b'\x00\x00\x80\x7f'  # 帧尾标识

# ==================== 映射配置 ====================
JOINT_ANGLE_RANGES = [
    (150.0, 205.0),  # 关节0
    (264.0, 308.0),   # 关节1
    (81.0, 145.0),  # 关节2
    (350.0, 406.0),  # 关节3
    (70.0, 130.0),  # 关节4
    (307.0, 367.0),  # 关节5
]

JOINT_REVERSED = [
    False,  # 关节0
    True,   # 关节1
    True,   # 关节2
    True,   # 关节3
    True,   # 关节4
    True,   # 关节5
]

JOINT_POS_MIN = 0
JOINT_POS_MAX = 1023


def normalize_angle(angle: float) -> float:
    """
    @brief 将原始角度限制在[-360°, 720°]范围内

    @param angle 输入角度
    @return 裁剪后的角度
    """
    if angle < -360.0:
        angle = -360.0
    elif angle > 720.0:
        angle = 720.0
    return angle


def map_angle_to_position(
    angle: float,
    angle_min: float,
    angle_max: float,
    reversed_flag: bool = False,
) -> int:
    """
    @brief 将单个角度值线性映射到关节控制值（0-1023）

    @param angle 当前角度
    @param angle_min 角度范围最小值
    @param angle_max 角度范围最大值
    @param reversed_flag 是否反向映射
    @return 映射后的关节控制值
    """
    angle = normalize_angle(angle)
    angle_min = normalize_angle(angle_min)
    angle_max = normalize_angle(angle_max)

    if abs(angle_max - angle_min) < 1e-6:
        ratio = 0.0
    else:
        if angle <= angle_min:
            ratio = 0.0
        elif angle >= angle_max:
            ratio = 1.0
        else:
            ratio = (angle - angle_min) / (angle_max - angle_min)

    if reversed_flag:
        ratio = 1.0 - ratio

    position = int(ratio * (JOINT_POS_MAX - JOINT_POS_MIN) + JOINT_POS_MIN)
    return max(JOINT_POS_MIN, min(JOINT_POS_MAX, position))


def map_angles_to_positions(angles: List[float]) -> List[float]:
    """
    @brief 将6个角度值映射到6个关节控制值（0-1023）

    @param angles 6个角度值列表
    @return 6个关节控制值列表
    """
    if len(angles) != 6:
        raise ValueError(f'需要6个角度值，实际收到{len(angles)}个')

    positions: List[float] = []
    for i in range(6):
        angle_min, angle_max = JOINT_ANGLE_RANGES[i]
        reversed_flag = JOINT_REVERSED[i]
        position = map_angle_to_position(angles[i], angle_min, angle_max, reversed_flag)
        positions.append(float(position))
    return positions


class ControllerReader:
    """
    @brief USB串口控制器数据读取类

    @details 通过串口读取控制器发送的6轴角度数据包，
             每个数据包包含6个float（小端序）和4字节帧尾标识。
             支持可选的低通滤波（一阶IIR滤波器）。
    """

    def __init__(self, port: str, baudrate: int = 115200,
                 timeout: float = 0.1, enable_filter: bool = True,
                 filter_alpha: float = 0.3):
        """
        @brief 初始化控制器读取器

        @param port         串口端口号（如 '/dev/ttyUSB0'）
        @param baudrate     波特率
        @param timeout      串口读取超时（秒）
        @param enable_filter 是否启用低通滤波
        @param filter_alpha  滤波系数（0-1），越小越平滑但响应越慢
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.enable_filter = enable_filter
        self.filter_alpha = filter_alpha
        self.serial: Optional[serial.Serial] = None
        self.buffer = bytearray()

        # 滤波器状态
        self.filtered_angles = [0.0] * 6
        self.is_first_read = True

        # 统计信息
        self.packet_count = 0
        self.error_count = 0
        self.last_angles = [0.0] * 6
        self.last_raw_angles = [0.0] * 6

    def connect(self) -> bool:
        """
        @brief 连接串口

        @return True=成功, False=失败
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            return True
        except Exception:
            return False

    def disconnect(self):
        """
        @brief 断开串口连接
        """
        if self.serial and self.serial.is_open:
            self.serial.close()

    def read_packet(self) -> Optional[tuple]:
        """
        @brief 读取串口缓冲区中所有数据，返回最新的一个完整数据包

        @details 一次调用会遍历缓冲区内的所有帧尾标识，逐个提取有效数据包，
                 最终只返回最新（最后）一个完整包。这样可以保证：
                 - 缓冲区不会无限增长
                 - 始终获取最新的控制器状态
                 - 不完整帧会被正确跳过

        @return (raw_angles, filtered_angles) 元组，如果无有效数据返回None
                raw_angles: 最新的原始6个浮点数列表
                filtered_angles: 滤波后的6个浮点数列表
        """
        if not self.serial or not self.serial.is_open:
            return None

        try:
            # 读取所有可用串口数据
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                self.buffer.extend(data)

            # 数据长度常量
            data_len = PACKET_SIZE - len(FRAME_TAIL)  # 24字节（6个float）
            latest_raw = None

            # 循环处理缓冲区中的所有帧，提取最新的有效包
            while True:
                frame_end = self.buffer.find(FRAME_TAIL)
                if frame_end == -1:
                    break

                if frame_end >= data_len:
                    # 帧尾前有足够数据，提取数据包
                    packet_start = frame_end - data_len
                    packet = self.buffer[packet_start:frame_end]
                    if len(packet) == data_len:
                        try:
                            raw_angles = list(struct.unpack('<6f', packet))
                            latest_raw = raw_angles
                        except struct.error:
                            self.error_count += 1

                # 无论是否成功提取，都跳过此帧尾继续查找下一个
                self.buffer = self.buffer[frame_end + len(FRAME_TAIL):]

            # 防止残留数据过多（无帧尾的垃圾数据）
            if len(self.buffer) > PACKET_SIZE * 4:
                self.buffer.clear()

            # 没有找到有效数据包
            if latest_raw is None:
                return None

            self.last_raw_angles = latest_raw.copy()

            # 应用低通滤波
            if self.enable_filter:
                if self.is_first_read:
                    self.filtered_angles = latest_raw.copy()
                    self.is_first_read = False
                else:
                    for i in range(6):
                        self.filtered_angles[i] = (
                            self.filter_alpha * latest_raw[i]
                            + (1 - self.filter_alpha) * self.filtered_angles[i]
                        )
                filtered = self.filtered_angles.copy()
            else:
                filtered = latest_raw.copy()

            self.packet_count += 1
            self.last_angles = filtered

            return (latest_raw, filtered)

        except Exception:
            self.error_count += 1
            return None

    def get_statistics(self) -> dict:
        """
        @brief 获取统计信息

        @return 统计信息字典
        """
        return {
            'packet_count': self.packet_count,
            'error_count': self.error_count,
            'buffer_size': len(self.buffer),
            'last_angles': self.last_angles,
            'last_raw_angles': self.last_raw_angles,
        }


class ControllerReaderNode(Node):
    """
    @brief 控制器数据读取ROS2节点

    @details 通过USB串口读取6轴控制器角度数据，将滤波结果映射为控制值后
             发布到 controller/angles 话题，同时可选发布原始角度到
             controller/angles_raw 话题。
             支持通过ROS2参数动态配置串口端口、波特率、滤波等。
    """

    def __init__(self):
        """
        @brief 初始化节点

        @details 声明ROS2参数、创建发布者、建立串口连接并启动读取线程。
        """
        super().__init__('controller_reader_node')

        # -------------------- 声明参数 --------------------
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('serial_baudrate', 115200)
        self.declare_parameter('serial_timeout', 0.1)
        self.declare_parameter('enable_filter', True)
        self.declare_parameter('filter_alpha', 0.3)
        self.declare_parameter('publish_raw', True)

        # -------------------- 读取参数 --------------------
        serial_port = self.get_parameter('serial_port').get_parameter_value().string_value
        serial_baudrate = self.get_parameter('serial_baudrate').get_parameter_value().integer_value
        serial_timeout = self.get_parameter('serial_timeout').get_parameter_value().double_value
        enable_filter = self.get_parameter('enable_filter').get_parameter_value().bool_value
        filter_alpha = self.get_parameter('filter_alpha').get_parameter_value().double_value
        self.publish_raw = self.get_parameter('publish_raw').get_parameter_value().bool_value

        # -------------------- 打印配置 --------------------
        self.get_logger().info('='*60)
        self.get_logger().info('  USB控制器数据读取节点')
        self.get_logger().info('='*60)
        self.get_logger().info(f'串口端口: {serial_port}')
        self.get_logger().info(f'波特率: {serial_baudrate}bps')
        self.get_logger().info(f'超时: {serial_timeout}s')
        self.get_logger().info(f'低通滤波: {"启用" if enable_filter else "禁用"}')
        if enable_filter:
            self.get_logger().info(f'滤波系数: {filter_alpha}')
        self.get_logger().info(f'发布原始数据: {"是" if self.publish_raw else "否"}')
        self.get_logger().info(f'话题: /controller/angles(映射值), /controller/angles_raw(原始角度)')
        self.get_logger().info('='*60)

        # -------------------- 创建发布者 --------------------
        self.pub_angles = self.create_publisher(
            Float32MultiArray, 'controller/angles', 10)
        if self.publish_raw:
            self.pub_angles_raw = self.create_publisher(
                Float32MultiArray, 'controller/angles_raw', 10)

        # -------------------- 创建控制器读取器 --------------------
        self.reader = ControllerReader(
            port=serial_port,
            baudrate=serial_baudrate,
            timeout=serial_timeout,
            enable_filter=enable_filter,
            filter_alpha=filter_alpha,
        )

        # -------------------- 连接串口 --------------------
        if not self.reader.connect():
            self.get_logger().error(
                f'串口连接失败: {serial_port}，请检查：\n'
                '  1. 控制器是否已连接\n'
                '  2. 串口号是否正确\n'
                '  3. 是否有权限访问串口（需要加入dialout组或使用sudo）'
            )
            raise RuntimeError(f'无法打开串口 {serial_port}')

        self.get_logger().info(f'串口连接成功: {serial_port} @ {serial_baudrate}bps')

        # -------------------- 发布计数 --------------------
        self._publish_count = 0

        # -------------------- 启动读取线程 --------------------
        self._running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

        # -------------------- 定时打印统计信息 --------------------
        self.create_timer(2.0, self._print_statistics)

    def _build_float_array_msg(self, data: List[float]) -> Float32MultiArray:
        """
        @brief 构造 Float32MultiArray 消息

        @param data 浮点数列表（6个角度值）
        @return 构造好的 Float32MultiArray 消息
        """
        msg = Float32MultiArray()
        dim = MultiArrayDimension()
        dim.label = 'angles'
        dim.size = len(data)
        dim.stride = len(data)
        msg.layout.dim = [dim]
        msg.layout.data_offset = 0
        # 使用 array.array('f') 确保与 Float32MultiArray.data 类型完全匹配
        msg.data = array.array('f', [float(x) for x in data])
        return msg

    def _read_loop(self):
        """
        @brief 串口读取主循环

        @details 在独立线程中运行，以1ms间隔读取串口数据，
                 每次读到新数据即发布话题。1ms轮询保证串口数据及时消费。
        """
        import time

        while self._running and rclpy.ok():
            try:
                result = self.reader.read_packet()

                if result is not None:
                    raw_angles, filtered_angles = result

                    # 发布映射后的控制值（由滤波角度映射得到）
                    mapped_positions = map_angles_to_positions(filtered_angles)
                    msg_mapped = self._build_float_array_msg(mapped_positions)
                    self.pub_angles.publish(msg_mapped)

                    # 发布原始角度
                    if self.publish_raw:
                        msg_raw = self._build_float_array_msg(raw_angles)
                        self.pub_angles_raw.publish(msg_raw)

                    self._publish_count += 1

            except Exception as e:
                self.get_logger().error(f'发布异常: {e}')

            # 1ms轮询间隔，保证串口缓冲区及时消费
            time.sleep(0.001)

    def _print_statistics(self):
        """
        @brief 定时打印统计信息
        """
        stats = self.reader.get_statistics()
        angles = stats['last_angles']
        mapped_positions = map_angles_to_positions(angles)
        self.get_logger().info(
            f'[统计] 解析:{stats["packet_count"]} '
            f'发布:{self._publish_count} '
            f'错误:{stats["error_count"]} '
            f'缓冲区:{stats["buffer_size"]}B'
        )
        if stats['packet_count'] > 0:
            self.get_logger().info(
                f'  控制值: [{int(mapped_positions[0])}, {int(mapped_positions[1])}, '
                f'{int(mapped_positions[2])}, {int(mapped_positions[3])}, '
                f'{int(mapped_positions[4])}, {int(mapped_positions[5])}]'
            )

    def destroy_node(self):
        """
        @brief 销毁节点时清理资源
        """
        self.get_logger().info('正在关闭控制器读取节点...')
        self._running = False
        if self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
        self.reader.disconnect()
        self.get_logger().info('控制器读取节点已关闭')
        super().destroy_node()


def main(args=None):
    """
    @brief 主函数入口

    @param args 命令行参数（默认为None）
    """
    rclpy.init(args=args)
    node = None

    try:
        node = ControllerReaderNode()
        rclpy.spin(node)
    except RuntimeError as e:
        print(f'[controller_reader] 启动失败: {e}')
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
