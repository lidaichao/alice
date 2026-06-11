import { StateCreator } from 'zustand';
import { Citation } from '../useChatStore';

export type MainView = 'chat' | 'operations' | 'settings';

export interface UISlice {
  isSidebarOpen: boolean;
  isRightPanelOpen: boolean;
  mainView: MainView;
  activeCitation: Citation | null;
  approvalPanelOpen: boolean;
  toggleSidebar: () => void;
  toggleRightPanel: () => void;
  setMainView: (view: MainView) => void;
  setActiveCitation: (citation: Citation | null) => void;
  setApprovalPanelOpen: (open: boolean) => void;
}

export const createUISlice: StateCreator<UISlice, [], [], UISlice> = (set) => ({
  isSidebarOpen: true,
  isRightPanelOpen: false,
  mainView: 'chat',
  activeCitation: null,
  approvalPanelOpen: false,

  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  toggleRightPanel: () => set((state) => ({ isRightPanelOpen: !state.isRightPanelOpen })),
  setMainView: (view) => set({ mainView: view }),
  setActiveCitation: (citation) => set({ activeCitation: citation, isRightPanelOpen: !!citation }),
  setApprovalPanelOpen: (open) => set({ approvalPanelOpen: open }),
});
