import { useCanvasStore } from './store.js';

function assert(cond: boolean, msg: string) {
  if (!cond) {
    throw new Error(`FAIL: ${msg}`);
  }
}

let fetchCalls = 0;

(globalThis as any).fetch = async () => {
  fetchCalls += 1;
  return { ok: true, status: 200, json: async () => ({ revision: 2 }) };
};

(async () => {
  useCanvasStore.setState({
    src: 'http://127.0.0.1:8081/api/canvas/project',
    revision: null,
    nodes: [],
    edges: [],
    error: null,
    loading: false,
    dirty: true,
  });
  fetchCalls = 0;
  await useCanvasStore.getState().save();
  assert(fetchCalls === 0, 'revision 为 null 时不应发出 PUT 请求');
  assert(
    useCanvasStore.getState().error === '请先加载画布后再保存',
    'revision 为 null 时应提示请先加载画布后再保存'
  );

  let lastBody: any = null;
  (globalThis as any).fetch = async (_url: string, init: any) => {
    fetchCalls += 1;
    lastBody = JSON.parse(init.body);
    return { ok: true, status: 200, json: async () => ({ revision: 2 }) };
  };

  useCanvasStore.setState({
    src: 'http://127.0.0.1:8081/api/canvas/project',
    revision: 1,
    nodes: [],
    edges: [],
    error: null,
    loading: false,
    dirty: true,
  });
  fetchCalls = 0;
  await useCanvasStore.getState().save();
  assert(fetchCalls === 1, 'revision 存在时应发出一次 PUT 请求');
  assert(lastBody && lastBody.base_version === 1, 'base_version 应等于当前 revision');

  console.log('store save guard: 2 checks passed');
})();
