# Queries, mutations and invalidation

<sub>_Doc written with the assistance of Claude AI :)_</sub>

How to read and change server data with [TanStack Query](https://tanstack.com/query), and how the cache stays up to date after a change. All examples use a Todo app.

To learn how to describe an endpoint and handle its errors, see [API requests and errors](./api-requests-and-errors.md).

## The idea

Query code is **centralized**, so every developer writes it the same way:

- **One file per domain** (`apps/web/src/queries/todo-query.ts`) holds the query keys, the endpoints, and the `queryOptions` / `mutationOptions` factories.
- **Components only consume these factories.** They never write a query key, a `queryFn` or an `invalidateQueries` call themselves.
- **Mutations declare what they invalidate** in `meta.invalidates`, and the query client refreshes those queries automatically.

## 1. Query keys

Query keys identify data in the cache. Build them with a small factory, from the most general key to the most specific:

```ts
// todo-query.ts
export const todoKeys = {
    all: () => ['todos'] as const,
    list: () => [...todoKeys.all(), 'list'] as const,
    detail: (id: string) => [...todoKeys.all(), 'detail', id] as const,
}
```

Keys are matched **by prefix**: `['todos']` covers `['todos', 'list']` and every `['todos', 'detail', id]`. This is what makes invalidation simple.

- Always go through the factory. Never write `['todos', 'list']` by hand in a component.
- Put every value the request depends on (id, filters, page…) in the key.

## 2. Queries: reading data

Expose each read as a `queryOptions` factory:

```ts
// todo-query.ts
export const todoQueries = {
    list: () =>
        queryOptions<Todo[], ErrorOf<typeof listTodos>>({
            queryKey: todoKeys.list(),
            queryFn: listTodos,
        }),
}
```

Use it in a component:

```tsx
const todos = useQuery(todoQueries.list())

if (todos.isPending) return <Skeleton />
if (todos.isError) return <Alert>{todos.error.message}</Alert>
return todos.data.map((todo) => <TodoItem key={todo.id} todo={todo} />)
```

The same factory works anywhere TanStack Query takes options, with the same key and types:

```ts
queryClient.prefetchQuery(todoQueries.list()) // e.g. on hover
await queryClient.ensureQueryData(todoQueries.list()) // e.g. in a route loader
queryClient.getQueryData(todoQueries.list().queryKey) // typed as Todo[] | undefined
```

## 3. Mutations: changing data

Expose each write as a `mutationOptions` factory, with what it invalidates:

```ts
// todo-query.ts
export const todoMutations = {
    create: () =>
        mutationOptions<Todo, ErrorOf<typeof createTodo>, InputOf<typeof createTodo>>({
            mutationKey: todoMutationKeys.create(),
            mutationFn: createTodo,
            meta: { invalidates: [todoKeys.all()] },
        }),
}
```

Use it in a component:

```tsx
const createTodo = useMutation(todoMutations.create())

// Fire and forget: the state is in createTodo.isPending / isError / error
createTodo.mutate({ body: newTodo })

// Or wait for the result, e.g. in a form submit
await createTodo.mutateAsync({ body: newTodo })
form.reset()
```

Component-specific side effects (resetting a form, closing a dialog, showing a toast) go in the component, through `mutateAsync` or the `onSuccess` / `onError` options of `mutate`. Cache refresh does not: it belongs in `meta.invalidates`.

## 4. Invalidation

### How it works

After a mutation **succeeds**, every key listed in `meta.invalidates` is invalidated:

- matching queries currently on screen are **refetched right away**;
- matching queries not on screen are marked stale and refetched **the next time they are used**.

The mutation stays `isPending` until those refetches are done. When `mutateAsync` resolves, the list on screen is already up to date.

### Choosing what to invalidate

| Mutation                       | `meta.invalidates`                  |
| ------------------------------ | ----------------------------------- |
| Changes todos                  | `[todoKeys.all()]`                  |
| Changes only one todo          | `[todoKeys.detail(id)]`             |
| Also affects another domain    | `[todoKeys.all(), statsKeys.all()]` |
| Changes nothing that is cached | omit `meta`                         |

- **Invalidate the whole domain by default** (`todoKeys.all()`). It is simple and rarely too costly. Narrow it only when refetching becomes noticeably expensive.
- **Think about other domains.** If creating a todo changes a dashboard counter, add that domain's key. Otherwise the counter stays stale.

### Invalidating on error

By default, a failed mutation invalidates nothing. Some requests can change data on the server and still fail, for example a batch update that stops halfway. For those, set `invalidateOnError`:

```ts
meta: { invalidates: [todoKeys.all()], invalidateOnError: true },
```

## Defaults

Configured once in `apps/web/src/queries/query-config.ts`:

- **`staleTime: 5s`**: data fetched less than 5 seconds ago is reused without a new request.
- **No refetch on window focus.**
- **Retries**: a query is retried once only when the server is unreachable or returns a 5xx. Mutations are never retried.

You can override any of these in a single `queryOptions` factory when a query needs it, e.g. `staleTime: Infinity` for data that never changes.

## Checklist for a new domain

1. Create `apps/web/src/queries/<domain>-query.ts`.
2. Add a `<domain>Keys` factory starting with `all: () => ['<domain>'] as const`.
3. Describe each endpoint with `queryMaker`.
4. Expose reads in `<domain>Queries` and writes in `<domain>Mutations`, each with its `meta.invalidates`.
5. In components, use only `useQuery(<domain>Queries.x())` and `useMutation(<domain>Mutations.x())`.

## References

- [The Query Options API](https://tkdodo.eu/blog/the-query-options-api)
- [Automatic Query Invalidation after Mutations](https://tkdodo.eu/blog/automatic-query-invalidation-after-mutations)
- [Effective React Query Keys](https://tkdodo.eu/blog/effective-react-query-keys)
