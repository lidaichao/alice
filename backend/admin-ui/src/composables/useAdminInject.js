import { inject, isRef } from 'vue';

export function useAdminInject() {
  const store = inject('adminStore');
  if (!store) throw new Error('adminStore not provided');
  return new Proxy(store, {
    get(target, prop) {
      const v = target[prop];
      if (typeof v === 'function') return v.bind(target);
      if (isRef(v)) return v.value;
      return v;
    },
    set(target, prop, value) {
      const v = target[prop];
      if (isRef(v)) {
        v.value = value;
        return true;
      }
      target[prop] = value;
      return true;
    },
  });
}
