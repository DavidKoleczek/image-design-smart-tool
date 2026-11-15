"""Which agent session a run on an image goes on in, for the capabilities that run an agent."""

from image_design.schemas import AgentProvider, ImageDesignError, ImageRunRecord


def resumed(runs: list[ImageRunRecord], resume_session: bool | str, name: str) -> ImageRunRecord | None:
    """The run among `runs` whose session the request continues, or None for a new session."""
    if resume_session is False:
        return None
    sessions = [run for run in runs if run.session_id is not None]
    if resume_session is True:
        if not sessions:
            raise ImageDesignError(
                f"Image {name} has no agent session to resume. Leave out resume_session to start a new one.",
                "no-such-session",
                name,
            )
        return sessions[-1]
    for run in reversed(sessions):
        if run.session_id == resume_session:
            return run
    known = ", ".join(dict.fromkeys(str(run.session_id) for run in reversed(sessions))) or "none"
    raise ImageDesignError(
        f"Image {name} has no session {resume_session!r}. Its sessions, latest first: {known}.",
        "no-such-session",
        name,
    )


def provider(given: AgentProvider | None, resumed: ImageRunRecord | None, name: str) -> AgentProvider | None:
    """The agent provider to run on: the one given, or the resumed session's, which a session must keep."""
    if resumed is None or resumed.agent_provider is None:
        return given
    if given is not None and given != resumed.agent_provider:
        raise ImageDesignError(
            f"Session {resumed.session_id} ran on the {resumed.agent_provider} agent provider, and a session goes on "
            f"only on the one it started on. Pass agent_provider={resumed.agent_provider!r}, or leave out "
            f"resume_session to start a new session on {given}.",
            "provider-mismatch",
            name,
        )
    return resumed.agent_provider
