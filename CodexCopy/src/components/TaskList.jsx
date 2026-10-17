import { PlusIcon, TrashIcon } from './icons';

// 左栏：任务列表（依据界面指南：管理并行任务、状态图标、删除）
const STATUS = {
  running: { icon: '🔄', label: 'Running', color: '#FA994C' },
  awaiting: { icon: '⏸', label: 'Awaiting confirmation', color: '#0169cc' },
  completed: { icon: '✅', label: 'Completed', color: '#00a240' },
  failed: { icon: '❌', label: 'Failed', color: '#e02e2a' },
  cancelled: { icon: '⏹', label: 'Cancelled', color: '#8f8f8f' },
};

export default function TaskList({ tasks, activeId, onSelect, onNew, onDelete }) {
  return (
    <div className="task-list">
      <div className="task-list-head">
        <span>Tasks</span>
        <button className="icon-btn sm" title="New task (⌘N)" onClick={onNew}>
          <PlusIcon size={13} />
        </button>
      </div>
      <div className="task-items">
        {tasks.map((t) => {
          const s = STATUS[t.status] || STATUS.running;
          return (
            <div key={t.id} className={'task-item' + (t.id === activeId ? ' active' : '')} onClick={() => onSelect(t.id)}>
              <span className="task-status" title={s.label}>{s.icon}</span>
              <span className="task-title">{t.title}</span>
              <button className="task-del" title="Delete task"
                onClick={(e) => { e.stopPropagation(); onDelete(t.id); }}>
                <TrashIcon size={12} />
              </button>
            </div>
          );
        })}
        {tasks.length === 0 && <div className="empty-note">No tasks yet</div>}
      </div>
    </div>
  );
}

export { STATUS };
