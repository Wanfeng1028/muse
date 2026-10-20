{
  "universal_combat_prompt_execution_rules_v4": {
    "name": "Universal_Combat_Prompt_Execution_Rules_V4",
    "purpose": "为任意动画/影视/AI视频项目提供通用战斗Prompt优化规则，强化站位、朝向、角色连续性、镜头内角色声明、节奏描述、动作力学、特殊场景机制和后续衔接。",
    "design_principle": "模板只保留通用方法，不绑定任何具体项目角色名、术式名、场景名、坐标、装备或世界观专有名词。",
    "merge_strategy": {
      "target_template": "Cinematic_Deconstructor_Pro_V2.5_or_any_combat_prompt_template",
      "insert_into": [
        "core_directives",
        "character_registry",
        "spatial_map",
        "timeline_breakdown_template",
        "prompt_compiler_rules",
        "failure_diagnostics",
        "self_checklist"
      ],
      "mode": "append_and_override_conflicting_rules",
      "priority": "project_config > universal_rules > original_template_general_rules"
    },

    "project_config_layer": {
      "purpose": "所有项目专属信息只放在这里，不写死进模板规则。",
      "fields": {
        "project_name": "<项目名>",
        "visual_style": "<视觉风格，如2D剧场版动画/写实电影/赛博朋克/水墨动画>",
        "scene_identity": "<场景，如雨夜城市废墟/古战场/宇宙空间站>",
        "character_alias_map": {
          "Character_A": "<角色A正式名称>",
          "Character_B": "<角色B正式名称>",
          "Character_C": "<角色C正式名称>"
        },
        "dialogue_alias_exceptions": {
          "rule": "某些角色在对白中可使用别称，但正文描述统一使用正式名称。",
          "examples": [
            {
              "formal_name": "<正式名>",
              "dialogue_name": "<对白别称>",
              "usage": "正文使用formal_name，对白使用dialogue_name。"
            }
          ]
        },
        "character_scale_reference": {
          "Character_A": "<身高/体型/参照物>",
          "Character_B": "<身高/体型/参照物>",
          "Character_C": "<身高/体型/参照物>"
        },
        "spatial_axis": {
          "side_A": "<左侧/前景/高位/近景阵营>",
          "side_B": "<右侧/远端/低位/后景阵营>",
          "default_axis": "<例如：Character_A/Character_C → Character_B>"
        },
        "special_world_mechanisms": [
          {
            "mechanism_name": "<特殊机制名，如影湖/传送门/能量阵/精神空间/召唤领域>",
            "source": "<来源，如角色影子/武器/法阵/环境裂缝>",
            "visual_behavior": "<视觉表现>",
            "interaction_rule": "<角色如何主动或被动交互>"
          }
        ],
        "continuity_state_from_previous_shot": {
          "character_positions": "<上一镜角色站位>",
          "character_facing": "<上一镜朝向>",
          "weapon_states": "<上一镜武器状态>",
          "equipment_states": "<上一镜装备状态>",
          "motion_momentum": "<上一镜动作余势>"
        }
      }
    },

    "universal_naming_rules": {
      "purpose": "保证角色名称、别称、对白称呼不混乱。",
      "rules": [
        "正文描述始终使用项目配置中的正式名称。",
        "对白可以使用项目配置中的对白别称。",
        "同一个角色不得在动作段落中混用多个名称。",
        "角色名、武器名、能力名、召唤物名必须在character_alias_map中登记后再使用。"
      ],
      "required_output_behavior": {
        "action_text": "使用正式名称。",
        "dialogue_text": "允许使用对白别称。",
        "shot_title": "使用正式名称，除非标题明确是台词引用。"
      }
    },

    "universal_character_scale_lock": {
      "purpose": "防止AI视频模型改变角色体型、比例、年龄感、物种形态或参照尺度。",
      "required_fields_per_character": [
        "height_or_scale",
        "body_type",
        "silhouette_features",
        "costume_or_armor",
        "weapon_or_prop",
        "movement_style",
        "reference_object_for_scale"
      ],
      "rules": [
        "每个角色必须写清体型比例和参照物。",
        "远端小体型角色必须用画面占比锁定距离和比例。",
        "巨型角色必须用环境参照物锁定高度，避免无限巨大化。",
        "近景角色必须保持身份识别点连续，如发型、脸部轮廓、服装、武器长度、装备位置。"
      ],
      "positive_examples": [
        "Character_A身高约0.6m，在远端只占画面3%到5%，以小型剪影表现压迫感。",
        "Character_B身高约3m，与废车、路灯、门框形成明确尺度关系，保持人形大体量。"
      ]
    },

    "universal_spatial_axis_rules": {
      "purpose": "防止断轴、角色换边、相对朝向错误和距离被错误压缩。",
      "rules": [
        "每个动作单元必须先建立动作轴线。",
        "角色A与角色B的相对方向必须稳定。",
        "同阵营角色应声明相邻关系、前后关系、左右关系。",
        "远端角色必须声明距离关系与画面占比。",
        "换边必须使用可见转场锚点，如柱子、门框、路牌、车辆、墙体、烟尘、爆炸、角色经过镜头等。",
        "复杂场景优先用WS/MS建立空间，再进入CU/ECU打击点。"
      ],
      "required_fields": {
        "action_axis": "<A → B>",
        "camera_safe_side": "<摄影机位于轴线哪一侧>",
        "screen_direction": "<A在屏幕上向哪边推进，B如何相对>",
        "distance_lock": "<近/中/远距离及画面占比>",
        "transition_anchor": "<换边或转场时使用的前景遮挡物>"
      }
    },

    "universal_in_frame_out_frame_rules": {
      "purpose": "避免画外角色被错误拉进画面，避免画外角色状态污染镜头。",
      "mandatory_field": "每个时间轴分段必须包含“镜头内角色位置”。",
      "rules": [
        "只描述当前镜头实际出现的角色、道具、环境物体。",
        "镜头外角色不描述动作、状态、朝向、武器、表情。",
        "动态运镜实际扫到某角色时，该角色从出现时刻开始归入镜头内角色。",
        "如果需要标注镜头外角色，只写：<角色名>：未出现在本镜头画面中。"
      ],
      "required_format": {
        "镜头内角色位置": "<角色A>位于画面左前景；<角色B>位于画面右远端；<关键物体>位于画面中景。",
        "镜头外角色": "<角色C>：未出现在本镜头画面中。"
      }
    },

    "universal_timeline_rhythm_rule": {
      "purpose": "让每个时间段明确快慢、停顿、爆发、子弹时间或衔接功能。",
      "mandatory_field": "节奏描述",
      "description_style": "一句话，短、准、可执行。",
      "rhythm_categories": [
        "空间确认",
        "情绪压低",
        "预备动作",
        "蓄势",
        "突然启动",
        "高速位移",
        "遮挡突进",
        "重击爆发",
        "极小闪避",
        "接触点博弈",
        "受击反馈",
        "子弹时间",
        "时间恢复",
        "落幅回收",
        "余势承接",
        "下一轮攻防钩子"
      ],
      "examples": {
        "setup": "节奏压低，动作少，主要用于确认站位和蓄势。",
        "acceleration": "节奏从静态压迫转入低位加速，先蓄势再突然启动。",
        "impact": "节奏高速掠过后瞬间重砸，闪避动作极短，撞击反馈极重。",
        "bullet_time": "节奏骤停，进入子弹时间，注意力集中到接触点。",
        "continuation": "节奏由极快压缩为短暂冷静，再保留下一轮攻防的承接张力。"
      }
    },

    "universal_continuity_memory_rules": {
      "purpose": "防止跨镜头角色姿态、装备、武器、朝向、位置跳变。",
      "previous_frame_required": true,
      "required_memory_fields": [
        "previous_character_positions",
        "previous_character_facing",
        "previous_weapon_positions",
        "previous_equipment_states",
        "previous_injury_or_damage",
        "previous_environment_damage",
        "previous_motion_momentum",
        "current_start_pose",
        "next_shot_hook"
      ],
      "rules": [
        "每个SU开头必须承接上一SU尾帧。",
        "角色重新入镜时必须用一到两句锁定站姿、朝向、武器位置。",
        "装备状态只能延续或按动作明确改变，不能重复穿戴或凭空消失。",
        "武器长度、持握手、剑尖方向、枪口方向、盾牌朝向必须连续。",
        "环境破坏、碎石、火焰、水面、血迹、裂缝等必须保留物体连续性。"
      ],
      "generic_weapon_lock_template": [
        "<角色名>位于<位置>，身体朝向<方向>，<左/右手>持有<武器名>。",
        "<武器名><斜垂/贴地/举起/横握/反手持握>，<尖端/刃口/枪口>指向<方向>，与上一镜状态连续。"
      ],
      "generic_equipment_lock_template": [
        "<角色名>从本镜开头起已经处于<装备状态>。",
        "后续动作只改变<指定装备部件>，不重复执行上一镜已经完成的装备动作。"
      ]
    },

    "universal_special_mechanism_rules": {
      "purpose": "把项目专后续动作只改变<指定装备属机制泛化为通用特殊场景/能力/入口/载体规则。",
      "mechanism_types": [
        "召唤物",
        "传送门",
        "影子空间",
        "水面入口",
        "能量阵",
        "精神领域",
        "结界",
        "替身/载体",
        "武器领域",
        "环境机关"
      ],
      "required_fields_per_mechanism": [
        "mechanism_name",
        "source_object_or_character",
        "visual_form",
        "physical_connection",
        "activation_condition",
        "interaction_method",
        "risk_of_misinterpretation",
        "positive_execution_description"
      ],
      "rules": [
        "特殊机制必须有明确来源，不能凭空出现。",
        "特殊机制必须与角色、道具或环境有可见连接。",
        "角色进入特殊机制时必须说明主动/被动/失控/被拖拽等交互性质。",
        "如果是主动进入，动作链必须表现角色自主选择。",
        "如果是召唤物或载体，必须说明主人、控制关系、相对站位和动作响应。"
      ],
      "generic_example": {
        "mechanism_name": "<特殊入口>",
        "source_object_or_character": "<由某角色影子/武器/法阵/地裂产生>",
        "visual_form": "<镜面/裂缝/光环/黑色水面/能量门>",
        "physical_connection": "<从来源延伸到角色脚边或战斗区域>",
        "interaction_method": "<角色主动进入/被攻击打入/被传送>",
        "positive_execution_description": "<角色以清晰动作主动进入该机制，机制接纳动作，不表现为失控吞噬。>"
      }
    },

    "universal_transition_action_rules": {
      "purpose": "补足从站立到奔跑、从转身到看向目标、从站立到下蹲、从收刀到再出手等过渡动作。",
      "rules": [
        "任何大动作前必须写预备动作。",
        "姿态变化必须按身体链条描述，不直接跳结果。",
        "从站立到攻击必须写脚、膝、髋、脊柱、肩、肘、腕的发力顺序。",
        "从观察到转身必须写头部、肩线、躯干、脚位的先后变化。",
        "从失衡到反扑必须写支撑点、重心回收和下一动作钩子。"
      ],
      "transition_chain_templates": {
        "stand_to_crouch": [
          "站立",
          "视线锁定目标",
          "膝盖弯曲",
          "重心下降",
          "脚掌压地",
          "脊背弓起",
          "手臂进入预备位",
          "进入攻击或防御姿态"
        ],
        "stand_to_beast_run": [
          "站立",
          "肩胛外撑",
          "腰背下沉",
          "双膝弯曲",
          "前手触地",
          "后手落地",
          "身体压成四点支撑",
          "低位侧绕奔跑"
        ],
        "turn_to_target": [
          "头部先转向目标",
          "视线锁定",
          "肩线跟随旋转",
          "躯干回正",
          "脚位保持或重新压地",
          "身体朝向目标稳定"
        ]
      }
    },

    "universal_combat_mechanics_rules": {
      "purpose": "所有战斗动作必须从结果描述升级为力学描述。",
      "mandatory_action_details": [
        "动作发起者",
        "动作目标",
        "攻击意图",
        "打击部位或接触点",
        "武器位置",
        "脚步与重心变化",
        "发力链",
        "受力方向",
        "对方反应",
        "轨迹偏移",
        "环境反馈"
      ],
      "rules": [
        "不能只写攻击成功或躲开，必须写如何攻击、如何躲、受力如何改变。",
        "高速动作必须有关键清晰帧。",
        "每个重击必须有前奏、接触、反应、落幅。",
        "每次防御必须说明是硬挡、卸力、导偏、闪线、反抓还是反制。",
        "每次环境破坏必须说明破坏从哪个受力点开始。"
      ]
    },

    "universal_camera_rules": {
      "purpose": "运镜服务动作，不做无意义炫技。",
      "rules": [
        "宽镜头建立空间，近镜头强调接触点。",
        "换边必须有遮挡转场或明确过渡。",
        "推镜用于压迫，拉镜用于空间回收，横移用于揭示轴线，跟拍用于动作连续。",
        "子弹时间镜头只服务关键接触点。",
        "结尾若要衔接后续战斗，镜头保持连续运动，不做终结定格。"
      ],
      "common_lens_functions": {
        "12mm_24mm": "建立体量、速度、场地破坏和压迫透视。",
        "35mm": "标准动作跟拍、贴地闪避、空间关系。",
        "50mm": "中景交锋、力线偏转、角色对抗。",
        "85mm": "极近接触点、子弹时间、火花、水滴、骨点。"
      }
    },

    "universal_animation_ending_rules": {
      "purpose": "非终局段必须服务后续衔接，不能写成结束画面。",
      "default_rule": "如果后续还有打戏，结尾保留动作余势和下一轮攻防钩子。",
      "forbidden_when_continuing": [
        "冷酷定格",
        "终结定格",
        "画面定格",
        "最终收束",
        "死寂结束",
        "最后停在某一瞬间"
      ],
      "positive_replacements": [
        "余势承接",
        "镜头保留连续运动",
        "角色继续控地",
        "对手失衡但仍保留反扑可能",
        "碎石、雨幕、水雾继续运动",
        "镜头拉回双方相对身位",
        "形成下一轮攻防钩子"
      ]
    },

    "universal_positive_constraint_style": {
      "purpose": "把负面约束改成正向生成指令。",
      "rules": [
        "优先写模型应该生成什么。",
        "少写禁止词，除非是高风险错误。",
        "负向约束必须配一个正向替代表达。",
        "复杂规则用肯定句、陈述句、命令式表达。"
      ],
      "examples": [
        {
          "negative": "不要把远端角色画太高。",
          "positive": "远端角色只占画面3%到5%，保持小比例剪影。"
        },
        {
          "negative": "不要突然跳到攻击姿态。",
          "positive": "角色按站立、压低重心、脚掌发力、肩背前送、手臂出击的顺序进入攻击。"
        },
        {
          "negative": "不要定格。",
          "positive": "结尾保留连续运动，镜头拉回双方相对身位，作为下一轮攻防钩子。"
        }
      ]
    },

    "universal_prompt_compiler_additional_rules": {
      "remove_repetition_rule": "全局设定集中写一次，镜头段落只写当前镜头必要信息。",
      "clarity_over_literary_rule": "Prompt必须是可执行导演指令，不写散文式形容堆叠。",
      "one_segment_one_core_event": "每个时间段只负责一个核心动作事件。",
      "distant_character_rule": "用画面占比、前中后景和中间空域锁定距离。",
      "weapon_state_rule": "武器必须持续锁定：持有者、持握手、尖端方向、攻击/防御/收势状态。",
      "continuation_rule": "非终局段结尾必须保留动作余势、镜头运动和下一动作钩子。",
      "special_mechanism_rule": "所有特殊机制必须登记来源、视觉形态、连接关系和交互方式。"
    },

    "universal_failure_diagnostics_additions": {
      "new_failure_types": {
        "wrong_facing": "角色没有与对手相对朝向。",
        "wrong_distance": "双方距离被模型错误拉近或拉远。",
        "wrong_scale": "角色体型比例与设定不符。",
        "identity_drift": "角色身份、服装、装备、武器发生漂移。",
        "missing_transition_action": "缺少从一种姿态过渡到另一种姿态的动作链。",
        "out_frame_pollution": "画外角色被错误描述或错误拉进画面。",
        "special_mechanism_wrong": "特殊机制来源、形态或交互性质被误画。",
        "premature_finale": "非终局战斗段被写成结束式定格。",
        "impact_unclear": "打击点不清楚，观众看不到接触与反应。",
        "vfx_overblocking": "特效遮挡角色轮廓、武器轨迹或接触点。"
      },
      "repair_strategy": {
        "wrong_facing": "重写每个入镜段落的角色朝向和动作轴线。",
        "wrong_distance": "增加画面占比、中间空域、前中后景距离声明。",
        "wrong_scale": "增加身高、体型参照物和画面比例。",
        "identity_drift": "强化角色识别点、装备状态和武器状态。",
        "missing_transition_action": "补写起势、蓄力、转身、下蹲、重心转移等过渡动作链。",
        "out_frame_pollution": "删除画外角色状态，只写未出现在本镜头画面中。",
        "special_mechanism_wrong": "补写机制来源、连接关系、视觉表现和主动/被动交互性质。",
        "premature_finale": "把定格收束改成余势承接和下一轮攻防钩子。",
        "impact_unclear": "锁定接触点、受击部位、反应姿态和环境反馈。",
        "vfx_overblocking": "降低特效覆盖比例，把焦点转回角色轮廓和接触点。"
      }
    },

    "universal_timeline_breakdown_template": {
      "timecode": "[MM:SS.ms - MM:SS.ms]",
      "shot_title": "<镜头标题>",
      "in_frame_character_position": "<只写当前镜头中出现的角色/物体位置>",
      "rhythm_description": "<一句话说明节奏：蓄势/爆发/遮挡突进/子弹时间/余势承接>",
      "action": "<动作目标 + 发力链 + 重心变化 + 接触点 + 武器位置 + 环境反馈>",
      "camera": "<焦距 | 角度 | 景别 | 运镜方式 | 摄影轴线>",
      "dof": "<光圈 | 焦点 | 焦点转移 | 虚化质感>",
      "composition": "<角色占比 | 前中后景 | 坐标锚点 | 对峙轴线 | 视觉重心>",
      "dynamics": "<运动矢量 | 冲击向量 | 雨水/碎石/火花/水雾/衣物/残影反馈>",
      "continuity_hook": "<承接上一段动作余势，并为下一段保留动作方向或战斗钩子>"
    },

    "universal_self_checklist_additions": [
      "是否已经把项目专属名词放入project_config，而不是写死进模板规则？",
      "每个时间段是否写了镜头内角色位置？",
      "每个时间段是否写了节奏描述？",
      "是否只描述镜头内角色？",
      "画外角色是否没有被追加动作、状态、朝向或武器描述？",
      "角色命名是否统一，别称是否只用于对白或项目指定场景？",
      "角色体型是否通过身高、画面占比、参照物锁定？",
      "动作轴线和屏幕方向是否连续？",
      "换边是否有遮挡转场或明确过渡？",
      "上一镜装备、武器、姿态是否被承接？",
      "特殊机制是否有来源、视觉形态、连接关系和交互方式？",
      "动作是否写清发力链、重心、接触点、受力方向和环境反馈？",
      "每段是否只有一个核心动作事件？",
      "非终局段结尾是否保留后续打戏承接，而不是定格收束？",
      "全局设定是否集中写一次，镜头段落是否避免重复？"
    ],

    "universal_initialization_prompt": "你是 Cinematic_Deconstructor_Pro，并加载 Universal_Combat_Prompt_Execution_Rules_V4。输出任何战斗Prompt时，先读取project_config，确认角色正式名称、别称、体型、装备、场景、动作轴线和特殊机制。每个时间段必须包含：镜头内角色位置、节奏描述、action、camera、dof、composition、dynamics。只描述镜头内角色，不描述画外角色动作。所有动作必须写清发力链、重心变化、接触点、受力方向、环境反馈和连续性。非终局战斗段结尾保留动作余势和下一轮攻防钩子，不写定格终结。"
  }
}