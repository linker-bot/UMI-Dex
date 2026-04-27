# Raw CAN bus frame captured from SocketCAN.
# Calibration and assembly happen offline in the Python pipeline.

std_msgs/Header header

uint32   arb_id
uint8    dlc
uint8[8] data
