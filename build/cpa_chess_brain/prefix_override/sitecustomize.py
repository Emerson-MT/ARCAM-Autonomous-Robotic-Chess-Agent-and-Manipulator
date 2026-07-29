import sys
if sys.prefix == '/usr':
    sys.real_prefix = sys.prefix
    sys.prefix = sys.exec_prefix = '/home/emersonmt/Documents/Projects/GRP-Chess-playing-arm/cpa_ws/install/cpa_chess_brain'
