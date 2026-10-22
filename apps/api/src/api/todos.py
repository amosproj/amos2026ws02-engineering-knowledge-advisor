from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, StringConstraints, field_validator

TodoTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TodoCreate(BaseModel):
    title: TodoTitle
    description: str = ""
    completed: bool = False


class Todo(TodoCreate):
    id: str


class TodoUpdate(BaseModel):
    title: TodoTitle | None = None
    description: str | None = None
    completed: bool | None = None

    @field_validator("title", "description", "completed", mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Todo fields cannot be null")
        return value


todos: dict[str, Todo] = {}

router = APIRouter(prefix="/api/todos", tags=["todos"])


@router.get("")
def list_todos() -> list[Todo]:
    return list(todos.values())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate) -> Todo:
    todo = Todo(id=str(uuid4()), **payload.model_dump())
    todos[todo.id] = todo
    return todo


@router.patch("/{todo_id}")
def update_todo(todo_id: str, payload: TodoUpdate) -> Todo:
    if todo_id not in todos:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")

    todo = todos[todo_id].model_copy(update=payload.model_dump(exclude_unset=True))
    todos[todo_id] = todo
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: str) -> Response:
    if todos.pop(todo_id, None) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
