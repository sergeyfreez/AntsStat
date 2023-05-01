import logging
import os

cur_dir = os.path.dirname(os.path.realpath(__file__))
fh = logging.FileHandler(os.path.join(cur_dir, "debug.log"))
fh.setLevel(logging.INFO)
st = logging.StreamHandler()
st.setLevel(logging.WARN)
logging.basicConfig(
    format='%(asctime)s, %(name)s %(levelname)s %(message)s',
    level=logging.INFO,
    handlers=[fh, st]
)