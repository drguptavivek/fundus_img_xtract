import type { WorkbenchAnnotation } from "./workbenchState";

export interface StoredPanelDraft {
  panelId: string;
  gradeId: number | null;
  selectedFeatureIds: number[];
  comment: string;
}

export interface StoredWorkbenchDraft {
  contextRevision: string;
  activeImageUuid: string;
  activePanelId: string;
  panels: StoredPanelDraft[];
  annotations: WorkbenchAnnotation[];
  updatedAt: string;
}

const DATABASE_NAME = "fundus-grading-workbench";
const STORE_NAME = "drafts";
const DATABASE_VERSION = 1;

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Draft storage is unavailable."));
  });
}

async function transaction<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>
): Promise<T> {
  const database = await openDatabase();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = database.transaction(STORE_NAME, mode);
      const request = run(tx.objectStore(STORE_NAME));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("Draft storage operation failed."));
    });
  } finally {
    database.close();
  }
}

export async function loadDraft(key: string): Promise<StoredWorkbenchDraft | null> {
  const result = await transaction<StoredWorkbenchDraft | undefined>("readonly", (store) => store.get(key));
  return result ?? null;
}

export async function saveDraft(key: string, draft: StoredWorkbenchDraft): Promise<void> {
  await transaction<IDBValidKey>("readwrite", (store) => store.put(draft, key));
}

export async function clearDraft(key: string): Promise<void> {
  await transaction<undefined>("readwrite", (store) => store.delete(key));
}
