import { StateCreator } from 'zustand';
import { Citation } from '../useChatStore';

export interface UISlice {
  isSidebarOpen: boolean;
  isRightPanelOpen: boolean;
  activeCitation: Citation | null;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
  setActiveCitation: (citation: Citation | null) => void;
}

export const createUISlice: StateCreator<UISlice, [], [], UISlice> = (set) => ({
  isSidebarOpen: true,
  isRightPanelOpen: false,
  activeCitation: null,

  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  toggleRightPanel: () => set((state) => ({ isRightPanelOpen: !state.isRightPanelOpen })),
  setActiveCitation: (citation) => set({ activeCitation: citation, isRightPanelOpen: !!citation }),
});
