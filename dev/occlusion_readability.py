"""Development adapter for the production visibility/review module."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game-sprite-animator/scripts'))
from sprite_anim.occlusion_review import visibility_metrics, arm_regions, frame_metrics
