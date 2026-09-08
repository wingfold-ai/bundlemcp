from pydantic import BaseModel, ConfigDict, Field


class StreamKey(BaseModel):
    """Where a live stream belongs and how it is addressed.

    List-changed fan-out selects streams by endpoint or bundle; signals from
    other replicas address one by its stream id, which is the session id for a
    handshake client's GET stream and the request id for a modern client's
    subscriptions/listen stream.
    """

    model_config = ConfigDict(frozen=True)

    endpoint_name: str = Field(description="Endpoint the stream was opened on")
    bundle_name: str = Field(description="Bundle that endpoint exposes")
    stream_id: str = Field(description="Session id or request id the stream is addressed by")
