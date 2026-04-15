# Calibrated hand joint state from CAN controller.
# positions[i] corresponds to names[i]; valid[i] indicates whether
# the encoder reported a good reading for that channel.

std_msgs/Header header

string[6] names
float64[6] positions
bool[6] valid
