import { z } from 'zod'

const STORAGE_KEY = 'machine-layout'

const panelLayoutSchema = z.object({
    treeWidth: z.number().positive().catch(320),
    treeCollapsed: z.boolean().catch(false),
    detailsWidth: z.number().positive().catch(288),
})

export type PanelLayout = z.output<typeof panelLayoutSchema>

export const DEFAULT_PANEL_LAYOUT: PanelLayout = panelLayoutSchema.parse({})

export function parsePanelLayout(raw: string | null): PanelLayout {
    if (raw === null) return DEFAULT_PANEL_LAYOUT
    try {
        const result = panelLayoutSchema.safeParse(JSON.parse(raw))
        return result.success ? result.data : DEFAULT_PANEL_LAYOUT
    } catch {
        return DEFAULT_PANEL_LAYOUT
    }
}

export function updatePanelLayout(
    layout: PanelLayout,
    treeWidth: number,
    detailsWidth: number,
): PanelLayout {
    return {
        treeWidth: treeWidth > 0 ? treeWidth : layout.treeWidth,
        treeCollapsed: treeWidth === 0,
        detailsWidth: detailsWidth > 0 ? detailsWidth : layout.detailsWidth,
    }
}

export function readPanelLayout() {
    try {
        return parsePanelLayout(localStorage.getItem(STORAGE_KEY))
    } catch {
        return DEFAULT_PANEL_LAYOUT
    }
}

export function savePanelLayout(layout: PanelLayout) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
    } catch {
        // Storage unavailable: the layout stays in memory for this session
    }
}
