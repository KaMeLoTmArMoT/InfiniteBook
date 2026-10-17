import pytest
from pydantic import ValidationError

from utils.pydantic_models import (
    ChapterPlanRequest,
    CharacterReq,
    CharactersRequest,
    PlotRequest,
    RefineRequest,
    SubmitFlux2Klein,
    SubmitRequest,
)


def test_refine_request_validation():
    # Valid
    req = RefineRequest(genre="Cyberpunk", idea="A neon city detective")
    assert req.genre == "Cyberpunk"

    # Too long idea
    with pytest.raises(ValidationError):
        RefineRequest(genre="Cyberpunk", idea="a" * 5000)

    # Too long genre
    with pytest.raises(ValidationError):
        RefineRequest(genre="a" * 100, idea="valid idea")

    # Empty
    with pytest.raises(ValidationError):
        RefineRequest(genre="", idea="")


def test_plot_and_characters_request_validation():
    # Valid
    p = PlotRequest(title="Title", genre="Sci-Fi", description="Desc")
    assert p.title == "Title"

    with pytest.raises(ValidationError):
        PlotRequest(title="a" * 250, genre="Sci-Fi", description="Desc")

    with pytest.raises(ValidationError):
        CharactersRequest(title="Title", genre="Sci-Fi", plot_summary="a" * 10000)


def test_chapter_plan_request_bounds():
    req = ChapterPlanRequest(
        chapter=1,
        title="Valid Title",
        genre="Fantasy",
        chapter_title="Chapter 1",
        chapter_summary="Summary",
    )
    assert req.chapter == 1

    # Invalid chapter numbers
    with pytest.raises(ValidationError):
        ChapterPlanRequest(
            chapter=0,
            title="Valid Title",
            genre="Fantasy",
            chapter_title="Chapter 1",
            chapter_summary="Summary",
        )

    with pytest.raises(ValidationError):
        ChapterPlanRequest(
            chapter=20000,
            title="Valid Title",
            genre="Fantasy",
            chapter_title="Chapter 1",
            chapter_summary="Summary",
        )


def test_submit_flux2_klein_bounds():
    # Valid
    s = SubmitFlux2Klein(prompt="A cool image")
    assert s.width == 1024
    assert s.height == 1024

    # Width too big
    with pytest.raises(ValidationError):
        SubmitFlux2Klein(prompt="A cool image", width=4096)

    # Width too small
    with pytest.raises(ValidationError):
        SubmitFlux2Klein(prompt="A cool image", width=32)

    # Steps out of range
    with pytest.raises(ValidationError):
        SubmitFlux2Klein(prompt="A cool image", steps=150)

    # Invalid filename prefix characters
    with pytest.raises(ValidationError):
        SubmitFlux2Klein(prompt="A cool image", filename_prefix="../../etc/passwd")


def test_submit_request_pipeline_literal():
    # Valid pipeline
    req = SubmitRequest(pipeline="flux2_klein_t2i", params={"width": 1024})
    assert req.pipeline == "flux2_klein_t2i"

    # Unknown pipeline rejected
    with pytest.raises(ValidationError):
        SubmitRequest(pipeline="unknown_pipeline", params={})


def test_character_req_bounds():
    # Valid
    c = CharacterReq(style_anchor="Cyberpunk")
    assert c.width == 768
    assert c.height == 1152

    # Negative or extreme dimensions
    with pytest.raises(ValidationError):
        CharacterReq(width=-10)

    with pytest.raises(ValidationError):
        CharacterReq(steps=0)
