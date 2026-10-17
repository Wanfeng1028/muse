import { useState } from 'react';
import { ChevronDown, SettingsIcon, CheckIcon } from './icons';
import { models, sandboxModes } from '../data/mock';

// 顶栏：项目选择 + 模型选择 + 沙盒模式 + 设置（依据界面指南）
export default function TopToolbar({ projects, activeProjectId, onProjectChange, model, onModelChange, sandbox, onSandboxChange, onOpenSettings }) {
  const [open, setOpen] = useState(null); // project | model | sandbox
  const active = projects.find((p) => p.id === activeProjectId);

  const Drop = ({ id, label, value, options, onPick }) => (
    <div style={{ position: 'relative' }}>
      <button className="toolbar-drop" onClick={() => setOpen(open === id ? null : id)}>
        <span className="td-label">{label}</span>
        <span className="td-value">{value}</span>
        <ChevronDown size={13} />
      </button>
      {open === id && (
        <>
          <div className="drop-mask" onClick={() => setOpen(null)} />
          <div className="drop-menu">
            {options.map((o) => (
              <div key={typeof o === 'string' ? o : o.id} className="drop-item"
                onClick={() => { onPick(typeof o === 'string' ? o : o.id); setOpen(null); }}>
                <span style={{ flex: 1 }}>{typeof o === 'string' ? o : o.name}</span>
                {(typeof o === 'string' ? o === value : o.id === activeProjectId) && <CheckIcon size={13} />}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="top-toolbar">
      <Drop id="project" label="Project" value={active?.name} options={projects} onPick={onProjectChange} />
      <Drop id="model" label="Model" value={model} options={models} onPick={onModelChange} />
      <Drop id="sandbox" label="Sandbox" value={sandbox} options={sandboxModes} onPick={onSandboxChange} />
      <span style={{ flex: 1 }} />
      <button className="icon-btn sm" title="Settings" onClick={onOpenSettings}>
        <SettingsIcon size={15} />
      </button>
    </div>
  );
}
