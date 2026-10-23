import { mutationOptions, queryOptions } from '@tanstack/react-query'
import { z } from 'zod'
import { queryMaker } from './query-maker'

export const todoSchema = z.object({
    id: z.string().min(1),
    title: z.string().trim().min(1),
    description: z.string(),
    completed: z.boolean(),
})

export const createTodoSchema = todoSchema.omit({ id: true })
export const updateTodoSchema = createTodoSchema.partial()
const todoParamsSchema = todoSchema.pick({ id: true })

export type Todo = z.output<typeof todoSchema>

export const todoKeys = {
    all: () => ['todos'] as const,
    list: () => [...todoKeys.all(), 'list'] as const,
}

export const todoMutationKeys = {
    create: () => [...todoKeys.all(), 'create'] as const,
    update: () => [...todoKeys.all(), 'update'] as const,
    delete: () => [...todoKeys.all(), 'delete'] as const,
}

const listTodos = queryMaker({
    method: 'GET',
    path: '/todos',
    response: z.array(todoSchema),
})

const createTodo = queryMaker({
    method: 'POST',
    path: '/todos',
    body: createTodoSchema,
    response: todoSchema,
})

const updateTodo = queryMaker({
    method: 'PATCH',
    path: '/todos/:id',
    params: todoParamsSchema,
    body: updateTodoSchema,
    response: todoSchema,
})

const deleteTodo = queryMaker({
    method: 'DELETE',
    path: '/todos/:id',
    params: todoParamsSchema,
    response: z.void(),
})

export const todoQueries = {
    list: () =>
        queryOptions({
            queryKey: todoKeys.list(),
            queryFn: listTodos,
        }),
}

export const todoMutations = {
    create: () =>
        mutationOptions({
            mutationKey: todoMutationKeys.create(),
            mutationFn: createTodo,
            meta: { invalidates: [todoKeys.all()] },
        }),
    update: () =>
        mutationOptions({
            mutationKey: todoMutationKeys.update(),
            mutationFn: updateTodo,
            meta: { invalidates: [todoKeys.all()] },
        }),
    delete: () =>
        mutationOptions({
            mutationKey: todoMutationKeys.delete(),
            mutationFn: deleteTodo,
            meta: { invalidates: [todoKeys.all()] },
        }),
}
