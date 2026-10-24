from pydantic import BaseModel


class TestResponse(BaseModel):
    pong: int
