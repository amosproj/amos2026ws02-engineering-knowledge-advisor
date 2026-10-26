# API requests and errors

<sub>_Doc written with the assistance of Claude AI :)_</sub>

How to call the FastAPI backend from the frontend, and how to send and handle errors. All examples use a Todo app.

Everything on the frontend side lives in `apps/web/src/queries/`, with one `<domain>-query.ts` file per domain (e.g. `todo-query.ts`).

## 1. A request without errors

**Backend:** write a normal FastAPI route.

```python
@v1_router.post("/todos", status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate) -> Todo:
    todo = Todo(id=str(uuid4()), **payload.model_dump())
    todos[todo.id] = todo
    return todo
```

**Frontend:** describe the endpoint with `queryMaker`, then expose it as a mutation (or `queryOptions` for a GET).

```ts
// todo-query.ts
const createTodo = queryMaker({
  method: "POST",
  path: "/v1/todos", // relative to /api; path params look like '/v1/todos/:id'
  body: createTodoSchema, // Zod schemas
  response: todoSchema,
});

export const todoMutations = {
  create: () =>
    mutationOptions<
      Todo,
      ErrorOf<typeof createTodo>,
      InputOf<typeof createTodo>
    >({
      mutationKey: ["todos", "create"],
      mutationFn: createTodo,
      meta: { invalidates: [["todos"]] }, // refetch todo queries on success
    }),
};
```

> Always write the `<Data, ErrorOf<…>, InputOf<…>>` generics: they are what makes `error` typed in your components.

**Component:**

```tsx
const createTodo = useMutation(todoMutations.create());

createTodo.mutate({
  body: { title: "Write the guide", description: "", completed: false },
});
```

## 2. The error format: RFC 9457

Every error response from the backend is a [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) problem, sent as `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Todo not found",
  "instance": "/api/v1/todos/12"
}
```

- `type` identifies the problem. `about:blank` means "nothing more specific than the HTTP status".
- `detail` (or `title` if there is no `detail`) becomes `error.message` on the frontend.
- Any other key is an extension member: data for the frontend.

On the frontend, every error has a `_tag` to narrow on and a `message` you can show to the user.

## 3. Simple errors

**Backend:** raise an `HTTPException` with a text `detail`. It is sent as an `about:blank` problem.

```python
raise HTTPException(status_code=404, detail="Todo not found")
```

**Frontend:** nothing to declare. Here, `_tag` is `'NotFound'` and `message` is `"Todo not found"`.

| `_tag`                                                                               | Happens when                                          |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `TooManyRequests` | 400, 401, 403, 404, 409, 429                          |
| `ServerError`                                                                        | 5xx                                                   |
| `UnexpectedStatus`                                                                   | Any other error status                                |
| `Validation`                                                                         | FastAPI rejected the input (422); see `error.issues`  |
| `Network`                                                                            | The server could not be reached                       |
| `Decode`                                                                             | The response does not match the `response` schema     |
| `InvalidInput`                                                                       | The input does not match its schema; nothing was sent |

The raw problem is still available in `error.problem` (e.g. `error.problem?.instance`).

## 4. Specific errors that carry data

When the frontend must recognise a specific error, or needs data with it, raise a `ProblemException` with its own `type`:

```python
raise ProblemException(Problem(
    type="urn:eka:problem:too-many-todos",  # identifies the error
    title="Too many todos",
    status=409,
    detail=f"Cannot create more than {MAX_TODOS} todos",
    max=MAX_TODOS,  # extension member: any data you need
))
```

Response:

```json
{
  "type": "urn:eka:problem:too-many-todos",
  "title": "Too many todos",
  "status": 409,
  "detail": "Cannot create more than 2 todos",
  "instance": "/api/v1/todos",
  "max": 2
}
```

- `type` identifies the error. Several errors can share the same status code. Any string works, as long as the frontend uses the exact same one.
- `detail` is what the user sees if the frontend does nothing special. Always include it.
- Declare the problem in the route's `responses` so it appears in the OpenAPI contract.

## 5. Declaring a specific error on the frontend

Declare the error with `defineProblem`, then add it to the `errors` of every endpoint that can return it:

```ts
// todo-query.ts
export class TooManyTodos extends defineProblem(
  "urn:eka:problem:too-many-todos",
  z.object({ max: z.number() }),
) {}

const createTodo = queryMaker({
  method: "POST",
  path: "/v1/todos",
  body: createTodoSchema,
  response: todoSchema,
  errors: [TooManyTodos],
});
```

What to keep in mind:

- **The `type` must match the backend exactly.** A typo is not reported: the error is then handled like an undeclared one. The `type` is also the error's `_tag`.
- **The schema only describes the extension members** (`max`). `type`, `title`, `detail`, etc. are handled for you.
- **Declaring is optional.** An undeclared problem still arrives as a standard error (`Conflict` here) with the backend `detail` as message. Declare it only when you need to react to it specifically or read its data.
- **If the backend changes the shape of the data**, the error is treated as undeclared and a warning is logged in the console.

## 6. Reading errors in a component

Check `_tag` to know which error you have:

```tsx
const createTodo = useMutation(todoMutations.create());

if (createTodo.error?._tag === "urn:eka:problem:too-many-todos") {
  const max = createTodo.error.data.max;
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
    if (error._tag === "Validation") showFieldErrors(error.issues);
  },
});
```

For any other error, just show `error.message`.

## Bonus: `matchError`

To handle several tags in one expression (handy in JSX), use `matchError`. It works like a `switch` on `_tag`, and each handler receives the correctly typed error:

```tsx
<AlertTitle>
  {matchError(createTodo.error, {
    "urn:eka:problem:too-many-todos": (error) =>
      `Limit of ${error.data.max} todos reached`,
    Network: () => "Server unreachable",
    orElse: (error) => error.message, // all other errors
  })}
</AlertTitle>
```

- Leave out `orElse` to force a handler for every possible tag: a missing one fails to compile.
- For a single tag, a plain `error._tag === '…'` check is enough.
