import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type SubmitEvent } from 'react'
import { todoMutations, todoQueries } from '../../queries/todo.query'

export const HomePage = () => {
    const todos = useQuery(todoQueries.list())
    const createTodo = useMutation(todoMutations.create())
    const updateTodo = useMutation(todoMutations.update())
    const deleteTodo = useMutation(todoMutations.delete())
    const [title, setTitle] = useState('')
    const [description, setDescription] = useState('')
    const isMutating = createTodo.isPending || updateTodo.isPending || deleteTodo.isPending

    const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault()
        createTodo.mutate(
            { body: { title, description, completed: false } },
            {
                onSuccess: () => {
                    setTitle('')
                    setDescription('')
                },
            },
        )
    }

    return (
        <section>
            <h1>Todos</h1>
            <form onSubmit={handleSubmit}>
                <fieldset disabled={isMutating}>
                    <legend>Add a todo</legend>
                    <label>
                        Title
                        <input
                            name="title"
                            value={title}
                            onChange={(event) => setTitle(event.target.value)}
                            required
                        />
                    </label>
                    <label>
                        Description
                        <textarea
                            name="description"
                            value={description}
                            onChange={(event) => setDescription(event.target.value)}
                        />
                    </label>
                    <button type="submit" disabled={!title.trim()}>
                        {createTodo.isPending ? 'Adding…' : 'Add'}
                    </button>
                </fieldset>
            </form>

            {[createTodo, updateTodo, deleteTodo].map((mutation, index) =>
                mutation.error ? (
                    <p role="alert" key={index}>
                        {mutation.error.message}
                    </p>
                ) : null,
            )}

            {todos.isPending && <p role="status">Loading…</p>}
            {todos.isError && (
                <p role="alert">
                    Unable to load todos: {todos.error.message}{' '}
                    <button
                        type="button"
                        disabled={todos.isFetching}
                        onClick={() => void todos.refetch()}
                    >
                        Retry
                    </button>
                </p>
            )}
            {todos.isFetching && !todos.isPending && <p role="status">Refreshing…</p>}
            {todos.data?.length === 0 && <p>No todos yet.</p>}
            <ul>
                {todos.data?.map((todo) => (
                    <li key={todo.id}>
                        <label>
                            <input
                                type="checkbox"
                                checked={todo.completed}
                                disabled={isMutating}
                                onChange={(event) =>
                                    updateTodo.mutate({
                                        params: { id: todo.id },
                                        body: { completed: event.target.checked },
                                    })
                                }
                            />
                            {todo.title}
                        </label>
                        <p>{todo.description}</p>
                        <button
                            type="button"
                            disabled={isMutating}
                            onClick={() => deleteTodo.mutate({ params: { id: todo.id } })}
                        >
                            Delete
                        </button>
                    </li>
                ))}
            </ul>
        </section>
    )
}
