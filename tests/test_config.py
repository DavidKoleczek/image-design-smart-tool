"""The person's defaults for the tool, and the order the image's agent picks an image model in by them."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.design_image import method as design_method
from image_design.cli import app
from image_design.schemas import ImageDesignConfig, ImageDesignError

runner = CliRunner()
UNSET = {"ready": False, "problem": "Set it up."}


def test_the_config_starts_at_the_tool_s_defaults_and_keeps_what_is_changed(config_directory: Path) -> None:
    before = lib.read_config()

    changed = lib.update_config(design_image_models=["chatgpt", "gpt-image-2.6-flare", "chatgpt"])
    untouched = lib.update_config()

    assert before == ImageDesignConfig()
    assert lib.config_path() == config_directory / "image-design" / "config.json"
    assert changed.design_image_models == ["chatgpt", "gpt-image-2.6-flare"]
    assert untouched == changed == lib.read_config()
    assert lib.update_config(design_image_models=[]) == ImageDesignConfig()


def test_an_image_model_the_agent_cannot_be_given_is_refused_and_nothing_is_changed() -> None:
    lib.update_config(design_image_models=["chatgpt"])

    with pytest.raises(ImageDesignError, match=r"'gpt-image-1' is not an image model design-image can be given\."):
        lib.update_config(design_image_models=["gpt-image-1", "chatgpt"])

    assert lib.read_config().design_image_models == ["chatgpt"]


def test_a_config_that_is_not_valid_says_where_it_is_and_how_to_go_back_to_the_defaults() -> None:
    lib.config_path().parent.mkdir(parents=True)
    lib.config_path().write_text('{"design_image_models": "chatgpt"}', encoding="utf-8")

    with pytest.raises(ImageDesignError, match="delete the file to go back to the tool's defaults") as raised:
        lib.list_image_methods()

    assert str(lib.config_path()) in str(raised.value)
    assert raised.value.reason == "bad-config"


def test_the_agent_is_given_the_first_image_model_of_the_order_that_is_set_up_and_makes_the_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    lib.update_config(design_image_models=["chatgpt", "gpt-image-2.6-flare"])
    methods = lib.list_image_methods()
    openai, chatgpt = methods.openai, methods.chatgpt
    preferred = lib.read_config().design_image_models

    assert methods.design.image_models == ["chatgpt", "gpt-image-2.6-flare", "gpt-image-2.6-sunburst"]
    assert methods.design.default_image_model == "chatgpt"
    assert design_method.image_model(None, "cactus.png", openai, chatgpt, preferred) == "chatgpt"
    # ChatGPT makes only a .png, so the next in the order makes the animation.
    assert design_method.image_model(None, "cactus.gif", openai, chatgpt, preferred) == "gpt-image-2.6-flare"
    assert design_method.image_model(None, "cactus.png", openai, chatgpt.model_copy(update=UNSET), preferred) == (
        "gpt-image-2.6-flare"
    )
    assert design_method.image_model("gpt-image-2.6-sunburst", "cactus.png", openai, chatgpt, preferred) == (
        "gpt-image-2.6-sunburst"
    )


def test_a_model_the_tool_no_longer_offers_is_passed_over(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    lib.config_path().parent.mkdir(parents=True)
    lib.config_path().write_text('{"design_image_models": ["gpt-image-1", "gpt-image-2.6-flare"]}', encoding="utf-8")

    design = lib.list_image_methods().design

    assert design.image_models == ["gpt-image-2.6-flare", "gpt-image-2.6-sunburst", "chatgpt"]
    assert design.default_image_model == "gpt-image-2.6-flare"


def test_the_cli_shows_and_changes_the_config() -> None:
    shown = runner.invoke(app, ["config"])
    changed = runner.invoke(app, ["config", "--design-image-models", "chatgpt, gpt-image-2.6-sunburst"])
    as_json = runner.invoke(app, ["config", "--json"])
    reset = runner.invoke(app, ["config", "--design-image-models", ""])
    refused = runner.invoke(app, ["config", "--design-image-models", "dall-e-3"])

    assert shown.exit_code == 0
    assert shown.output == (f"Kept in {lib.config_path()}\n- design_image_models: none, so the tool's own order\n")
    assert changed.output.endswith("- design_image_models: chatgpt, gpt-image-2.6-sunburst\n")
    assert ImageDesignConfig.model_validate_json(as_json.output).design_image_models == [
        "chatgpt",
        "gpt-image-2.6-sunburst",
    ]
    assert reset.output.endswith("- design_image_models: none, so the tool's own order\n")
    assert refused.exit_code == 1
    assert lib.read_config() == ImageDesignConfig()
