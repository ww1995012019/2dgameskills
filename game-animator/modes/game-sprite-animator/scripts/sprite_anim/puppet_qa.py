"""Run the existing puppet checks with one bounded preparation cache per clip."""
from .frame_checks import FrameContext
from .occlusion_review import clip_candidates
from .puppet_check import (check_layers, check_motion, check_hands, check_core,
                           check_neck, check_connections, check_attachments)


def check_clips(renderer, spec, clips, names, rendered, fps, overrides):
    problems = check_layers(renderer.art.puppet)
    candidates = []
    registered = spec.get('puppet', {}).get('connection_skinning') == 'registered_garment_v3'
    attachments = spec.get('puppet', {}).get('attachment_checks', False)
    for name in names:
        clip, frames = clips[name], rendered[name]['frames']
        rate = overrides.get(name, fps)
        with FrameContext(renderer, clip, len(frames), rate) as context:
            problems += check_motion(renderer, clip, len(frames), rate, context=context)
            problems += check_hands(renderer, spec, clip, frames, rate, context=context)
            problems += check_core(renderer, clip, frames, rate, context=context)
            problems += check_neck(renderer, clip, len(frames), rate, context=context)
            if registered:
                problems += check_connections(renderer, clip, len(frames), rate, context=context)
            if attachments:
                problems += check_attachments(renderer, clip, len(frames), rate, context=context)
                candidates += clip_candidates(renderer, clip, len(frames), rate, context=context)
    return problems, candidates
