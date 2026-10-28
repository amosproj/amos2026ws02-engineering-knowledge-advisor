from pydantic import BaseModel


class TestRequest(BaseModel):
    ping: int
