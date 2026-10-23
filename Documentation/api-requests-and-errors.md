# API requests and errors

<sub>_Doc written with the assistance of Claude AI :)_</sub>

How to call the FastAPI backend from the frontend, and how to send and handle errors. All examples use a Todo app.

Everything on the frontend side lives in `apps/web/src/queries/`, with one `<domain>-query.ts` file per domain (e.g. `todo-query.ts`).

## 1. A request without errors

**Backend:** write a normal FastAPI route.

```python
@router.post("", status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate) -> Todo:
    todo = Todo(id=str(uuid4()), **payload.model_dump())
    todos[todo.id] = todo
    return todo
```

**Frontend:** describe the endpoint with `queryMaker`, then expose it as a mutation (or `queryOptions` for a GET).

```ts
// todo-query.ts
const createTodo = queryMaker({
    method: 'POST',
    path: '/todos', // relative to /api; path params look like '/todos/:id'
    body: createTodoSchema, // Zod schemas
    response: todoSchema,
})

export const todoMutations = {
    create: () =>
        mutationOptions<Todo, ErrorOf<typeof createTodo>, InputOf<typeof createTodo>>({
            mutationKey: ['todos', 'create'],
            mutationFn: createTodo,
            meta: { invalidates: [['todos']] }, // refetch todo queries on success
        }),
}
```

> Always write the `<Data, ErrorOf<…>, InputOf<…>>` generics: they are what makes `error` typed in your components.

**Component:**

```tsx
const createTodo = useMutation(todoMutations.create())

createTodo.mutate({ body: { title: 'Write the guide', description: '', completed: false } })
```

## 2. Simple errors

**Backend:** raise an `HTTPException` with a text `detail`.

```python
raise HTTPException(status_code=404, detail="Todo not found")
```

**Frontend:** nothing to declare. Every error has a `_tag` and a `message` you can show to the user. Here, `_tag` is `'NotFound'` and `message` is `"Todo not found"`.

| `_tag`                                                                               | Happens when                                          |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `TooManyRequests` | 400, 401, 403, 404, 409, 429                          |
| `ServerError`                                                                        | 5xx                                                   |
| `UnexpectedStatus`                                                                   | Any other error status                                |
| `Validation`                                                                         | FastAPI rejected the input (422); see `error.issues`  |
| `Network`                                                                            | The server could not be reached                       |
| `Decode`                                                                             | The response does not match the `response` schema     |
| `InvalidInput`                                                                       | The input does not match its schema; nothing was sent |

## 3. Tagged errors that carry data

When the frontend must recognise a specific error, or needs data with it, send an object as `detail` with a `_tag`:

```python
raise HTTPException(
    status_code=400,
    detail={
        "_tag": "TooManyTodos",                            # name of the error
        "message": f"Cannot create more than {MAX_TODOS} todos",
        "max": MAX_TODOS,                                  # any data you need
    },
)
```

- `_tag` identifies the error. Several errors can share the same status code.
- `message` is what the user sees if the frontend does nothing special. Always include it.
- Any other key is data for the frontend.

## 4. Declaring a tagged error on the frontend

Declare the error with `defineError`, then add it to the `errors` of every endpoint that can return it:

```ts
// todo-query.ts
export class TooManyTodos extends defineError('TooManyTodos', z.object({ max: z.number() })) {}

const createTodo = queryMaker({
    method: 'POST',
    path: '/todos',
    body: createTodoSchema,
    response: todoSchema,
    errors: [TooManyTodos],
})
```

What to keep in mind:

- **The tag must match the backend exactly** (`'TooManyTodos'`). A typo is not reported: the error is then handled like an undeclared one.
- **The schema only describes your data** (`max`). `_tag` and `message` are handled for you.
- **Declaring is optional.** An undeclared tagged error still arrives with the backend `message`. Declare it only when you need to react to it specifically or read its data.
- **If the backend changes the shape of the data**, the error is treated as undeclared and a warning is logged in the console.

## 5. Reading errors in a component

Check `_tag` to know which error you have:

```tsx
const createTodo = useMutation(todoMutations.create())

if (createTodo.error?._tag === 'TooManyTodos') {
    const max = createTodo.error.data.max
}
```

**`data.max` is really typed as `number`**, straight from the Zod schema of `TooManyTodos`. There is no cast and no `any`:

- your editor autocompletes `error.data.` with `max`;
- if the schema changes (say `max` becomes `limit`), every usage fails to compile;
- outside the `_tag` check, `error.data.max` does not compile, because other errors have no such field;
- a tag the endpoint cannot return, such as `error._tag === 'Typo'`, does not compile either.

The same applies everywhere you get the error, for example in `onError`:

```ts
createTodo.mutate(input, {
    onError: (error) => {
        if (error._tag === 'Validation') showFieldErrors(error.issues)
    },
})
```

For any other error, just show `error.message`.

## Bonus: `matchError`

To handle several tags in one expression (handy in JSX), use `matchError`. It works like a `switch` on `_tag`, and each handler receives the correctly typed error:

```tsx
<AlertTitle>
    {matchError(createTodo.error, {
        TooManyTodos: (error) => `Limit of ${error.data.max} todos reached`,
        Network: () => 'Server unreachable',
        orElse: (error) => error.message, // all other errors
    })}
</AlertTitle>
```

- Leave out `orElse` to force a handler for every possible tag: a missing one fails to compile.
- For a single tag, a plain `error._tag === '…'` check is enough.
