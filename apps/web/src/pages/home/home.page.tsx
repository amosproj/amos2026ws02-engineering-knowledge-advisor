import { useMutation, useQuery } from '@tanstack/react-query'
import { PlusSignIcon, Delete02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { z } from 'zod'
import {
    Alert,
    AlertDescription,
    AlertTitle,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Checkbox,
    Empty,
    EmptyDescription,
    EmptyHeader,
    EmptyMedia,
    EmptyTitle,
    Skeleton,
    useAppForm,
} from '@components'
import { cn } from 'cn'
import { todoMutations, todoQueries } from '../../queries/todo-query'

const titleSchema = z.string().min(1, 'Title is required')

export const HomePage = () => {
    const todos = useQuery(todoQueries.list())
    const createTodo = useMutation(todoMutations.create())
    const updateTodo = useMutation(todoMutations.update())
    const deleteTodo = useMutation(todoMutations.delete())

    const form = useAppForm({
        defaultValues: {
            title: '',
            description: '',
        },
        onSubmit: async ({ value, formApi }) => {
            await createTodo.mutateAsync({
                body: { title: value.title, description: value.description, completed: false },
            })
            formApi.reset()
        },
    })

    return (
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
            <Card>
                <CardHeader>
                    <CardTitle>Add a todo</CardTitle>
                    <CardDescription>Track things you need to get done.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form
                        onSubmit={(event) => {
                            event.preventDefault()
                            event.stopPropagation()
                            void form.handleSubmit()
                        }}
                        className="flex flex-col gap-4"
                    >
                        <form.AppField name="title" validators={{ onChange: titleSchema }}>
                            {(field) => (
                                <field.InputForm
                                    label="Title"
                                    placeholder="e.g. Review the knowledge base schema"
                                />
                            )}
                        </form.AppField>
                        <form.AppField name="description">
                            {(field) => (
                                <field.TextareaForm
                                    label="Description"
                                    placeholder="Optional details…"
                                    rows={3}
                                />
                            )}
                        </form.AppField>
                        <form.AppForm>
                            <form.SubscribeForm pendingContent="Adding…">
                                Add todo
                            </form.SubscribeForm>
                        </form.AppForm>
                    </form>
                </CardContent>
            </Card>

            {[createTodo, updateTodo, deleteTodo].map((mutation, index) =>
                mutation.error ? (
                    <Alert key={index} variant="destructive" role="alert">
                        <AlertTitle>Something went wrong</AlertTitle>
                        <AlertDescription>{mutation.error.message}</AlertDescription>
                    </Alert>
                ) : null,
            )}

            {todos.isPending && (
                <div className="flex flex-col gap-2" role="status" aria-label="Loading todos">
                    <Skeleton className="h-16 w-full" />
                    <Skeleton className="h-16 w-full" />
                    <Skeleton className="h-16 w-full" />
                </div>
            )}

            {todos.isError && (
                <Alert variant="destructive" role="alert">
                    <AlertTitle>Unable to load todos</AlertTitle>
                    <AlertDescription className="flex items-center gap-2">
                        {todos.error.message}
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={todos.isFetching}
                            onClick={() => void todos.refetch()}
                        >
                            Retry
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            {todos.isFetching && !todos.isPending && (
                <p role="status" className="text-muted-foreground text-sm">
                    Refreshing…
                </p>
            )}

            {todos.data?.length === 0 && (
                <Empty className="border">
                    <EmptyHeader>
                        <EmptyMedia variant="icon">
                            <HugeiconsIcon icon={PlusSignIcon} strokeWidth={2} />
                        </EmptyMedia>
                        <EmptyTitle>No todos yet</EmptyTitle>
                        <EmptyDescription>
                            Add your first todo using the form above.
                        </EmptyDescription>
                    </EmptyHeader>
                </Empty>
            )}

            {todos.data && todos.data.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Todos</CardTitle>
                        <CardDescription>
                            {todos.data.filter((todo) => todo.completed).length} of{' '}
                            {todos.data.length} completed
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                        {todos.data.map((todo) => (
                            <div
                                key={todo.id}
                                className="flex items-start gap-3 rounded-xl border p-3"
                            >
                                <Checkbox
                                    checked={todo.completed}
                                    onCheckedChange={(checked) =>
                                        updateTodo.mutate({
                                            params: { id: todo.id },
                                            body: { completed: checked },
                                        })
                                    }
                                    className="mt-0.5"
                                    aria-label={`Mark "${todo.title}" as ${todo.completed ? 'active' : 'completed'}`}
                                />
                                <div className="min-w-0 flex-1 space-y-1">
                                    <p
                                        className={cn(
                                            'text-sm font-medium',
                                            todo.completed && 'text-muted-foreground line-through',
                                        )}
                                    >
                                        {todo.title}
                                    </p>
                                    {todo.description ? (
                                        <p className="text-muted-foreground text-sm">
                                            {todo.description}
                                        </p>
                                    ) : null}
                                </div>
                                <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label={`Delete "${todo.title}"`}
                                    onClick={() => deleteTodo.mutate({ params: { id: todo.id } })}
                                >
                                    <HugeiconsIcon icon={Delete02Icon} strokeWidth={2} />
                                </Button>
                            </div>
                        ))}
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
