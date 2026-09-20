import sys
sys.path.insert(0, 'e:/alex')
from tools.youtube_tools import search_youtube
try:
    results = search_youtube("The Local Train Choo Lo", limit=1)
    print("Results:", results)
except Exception as e:
    print("Error:", e)
