import sys
import time
import itertools
import random

def storming_progress_bar(current, total, start_time, update_message=""):
    # Frames to simulate walking
    rebel_frames = itertools.cycle(['🚶', '🚶‍♂️', '🚶‍♀️', '🧍'])
    rebel = next(rebel_frames)

    # Static icons
    bastille = '🏰'
    
    # Length of the progress bar
    bar_length = 30
    filled = int(bar_length * current // total)
    road = '·' * (bar_length - filled)
    
    # Random bombs on the road
    bomb_chance = 0.15
    bombs = ''.join('💣' if random.random() < bomb_chance else ' ' for _ in range(filled))

    # Explode if done
    if current >= total:
        impact = '💥'
    else:
        impact = ''
    
    # Time tracking
    elapsed = time.time() - start_time
    time_str = f"{elapsed:5.2f}s"

    # Final rendering
    bar = f"\r{next(rebel_frames)}{bombs}{road}{bastille}{impact} [{current}/{total}] {time_str} {update_message}"
    sys.stdout.write(bar)
    sys.stdout.flush()

# Example usage
if __name__ == "__main__":
    import math

    total = 100
    current = 0
    start = time.time()

    while current <= total:
        msg = f"Computing sqrt({current}) = {math.sqrt(current):.2f}"
        storming_progress_bar(current, total, start, update_message=msg)
        time.sleep(0.05)
        current += 1

    sys.stdout.write("\n🏁 Done! Vive la Révolution!\n")
