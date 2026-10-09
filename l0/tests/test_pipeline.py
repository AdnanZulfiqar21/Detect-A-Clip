"""Pipeline behaviour on synthetic fixtures (AI-07 distinct states, CAP-03 analogue,
cancellation). Accuracy itself is measured by the LAB runner, not asserted here."""
import pytest

from dac_l0.index.builder import build_index
from dac_l0.index.descriptors import DescriptorFamily
from dac_l0.index.retrieval import FlatRetriever
from dac_l0.pipeline import Delivered, recognise
from dac_l0.schemas import ResultState
from dac_l0.synth.generator import Clip, Edition, EditionKind, PrivateScreen, PrivateScreenKind, blank_frame, gallery_works


@pytest.fixture(scope="module")
def retr():
    works = gallery_works(4)
    return FlatRetriever(build_index([Edition(w, k) for w in works for k in EditionKind], DescriptorFamily.HASH64)), works


def frames(render, seconds=8.0, fps=10):
    return [Delivered(int(i * 1000 / fps), render(i / fps)) for i in range(int(seconds * fps))]


def test_clean_clip_names_true_work_and_never_outside_catalogue(retr):
    r, works = retr
    clip = Clip(Edition(works[2], EditionKind.THEATRICAL), 20.0, 8.0)
    res, hyps, summ = recognise("s", 1, frames(clip.frame_at), r, 0)
    assert res.state in (ResultState.VERIFIED_MATCH, ResultState.POSSIBLE_MATCH)
    assert res.candidate_work_id == works[2].work_id
    assert summ.selected <= 17  # ≤2 fps over 8 s


def test_blank_feed_is_unsupported_capture(retr):
    r, _ = retr
    res, _, _ = recognise("s", 1, frames(lambda t: blank_frame(0)), r, 0)
    assert res.state == ResultState.UNSUPPORTED_CAPTURE
    assert res.candidate_work_id is None


def test_static_frame_of_known_work_is_insufficient_signal(retr):
    r, works = retr
    still = works[1].render_frame(30.0)
    res, _, _ = recognise("s", 1, frames(lambda t: still), r, 0)
    assert res.state == ResultState.INSUFFICIENT_SIGNAL


@pytest.mark.parametrize("kind", list(PrivateScreenKind))
def test_synthetic_private_screens_never_produce_a_title(retr, kind):
    r, _ = retr
    ps = PrivateScreen(kind, 1)
    res, _, _ = recognise("s", 1, frames(lambda t: ps.render_frame(t)), r, 0)
    assert res.candidate_work_id is None


def test_cancellation_during_work_publishes_only_cancelled(retr):
    r, works = retr
    clip = Clip(Edition(works[0], EditionKind.THEATRICAL), 10.0, 8.0)
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 30

    res, hyps, _ = recognise("s", 1, frames(clip.frame_at), r, 0, is_cancelled=cancelled)
    assert res.state == ResultState.CANCELLED
    assert res.candidate_work_id is None and hyps == []
