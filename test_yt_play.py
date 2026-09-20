import sys
sys.path.insert(0, 'e:/alex')
from tools.youtube_tools import youtube_play
try:
    result = youtube_play({"query": "Choo Lo The Local Train"})
    print("Result:", result)
except Exception as e:
    print("Error:", e)
