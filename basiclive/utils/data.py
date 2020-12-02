import itertools


def parse_frames(frame_string):
    frames = []
    if frame_string:
        for w in frame_string.split(','):
            v = list(map(int, w.split('-')))
            if len(v) == 2:
                frames.extend(range(v[0], v[1] + 1))
            elif len(v) == 1:
                frames.extend(v)
    return frames


def frame_ranges(frame_list):
    for a, b in itertools.groupby(enumerate(frame_list), lambda xy: xy[1] - xy[0]):
        b = list(b)
        yield b[0][1], b[-1][1]