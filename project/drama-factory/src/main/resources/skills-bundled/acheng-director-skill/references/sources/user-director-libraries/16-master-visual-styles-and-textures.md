# 16｜名家艺术风格、画风与材质质感终极档案库（Master Visual Styles & Texture Engine）
# ——专为 AI 影视生产、超长提示词编译与防幻觉设计的微表面与光学工程规格

> **版本**：v1.0.0-master-complete  
> **适用范围**：电影摄影机光学、胶片质感、物理滤镜、影视大师风格、专业原画作画（Sakuga）、前沿游戏渲染、物理材质 BRDF 响应解剖  
> **核心使命**：彻底消灭“8K, masterpiece, cinematic”等空洞垃圾词汇。通过精确到物理光学、镜头镀膜、感光乳剂、炭笔压感线与材质次表面散射的工程化描述，为 AI 视频扩散模型（如 MiniMax H3 Ref2VA、Sora 等）提供绝对稳定、防漂移、具备院线级质感的提示词底层原料。

---

## 目录索引

1. [光学摄影机、胶片基底与物理滤镜工程库（Cinematic Optics & Filter Specs）](#一光学摄影机胶片基底与物理滤镜工程库)
2. [世界院线级电影大师摄影与光影风格库（Cinematic Masters & Lighting Styles）](#二世界院线级电影大师摄影与光影风格库)
3. [专业原画作画（Sakuga）与动画监督大师风格矩阵（Sakuga Masters & Animation Directives）](#三专业原画作画sakuga与动画监督大师风格矩阵)
4. [前沿数字媒介与顶级游戏视觉美学（Cutting-Edge CG & Game Aesthetics）](#四前沿数字媒介与顶级游戏视觉美学)
5. [物理材质微表面与 BRDF 光学响应解剖（Micro-Surface & BRDF Material Engine）](#五物理材质微表面与-brdf-光学响应解剖)
6. [即插即用的工业级万能质感组装公式（Production Prompt Blueprints）](#六即插即用的工业级万能质感组装公式)

---

## 一、 光学摄影机、胶片基底与物理滤镜工程库

在扩散模型中，直接写“film look”往往会导致廉价的复古噪点贴图。必须使用真实的**镜头型号、胶片感光乳剂与滤镜物理特性**来精准锚定潜空间：

### 1. 经典电影镜头光学系统（Lens Optics & Aberrations）
* **Panavision C-Series Anamorphic（变形宽银幕镜头系统，2.39:1）**：
  * *光学特征*：经典的 2 倍水平压缩，背景点光源呈现垂直椭圆形散景（Oval Bokeh），强光源直射时产生标志性的水平蓝色拉丝眩光（Horizontal Blue Streak Flares），画面边缘带有轻微桶形畸变与暗角。
  * *H3 标准描述*：`Captured on Panavision C-series anamorphic prime lenses, 2.39:1 widescreen scope, rendering characteristic vertical oval bokeh, subtle peripheral barrel distortion, and organic horizontal cyan streak flares across direct light sources.`
* **Cooke S4/i Prime（英国库克镜头，传奇“Cooke Look”）**：
  * *光学特征*：以极致温暖、柔和的皮肤高光衰减闻名，锐利却不生硬，暗部过渡平滑如天鹅绒，极富呼吸感与人情味。
  * *H3 标准描述*：`Shot on Cooke S4/i prime lenses, delivering the signature warm 'Cooke Look' with gentle skin-tone fall-off, velvet shadow transitions, and delicate spherical micro-contrast.`
* **Lomo Round-Front Anamorphic（苏联复古洛莫变形镜头）**：
  * *光学特征*：强烈的边缘旋焦（Swirly Bokeh）、明显的像散（Astigmatism）与边缘失光，高光处泛出神秘的紫红与金黄色暖晕。
  * *H3 标准描述*：`Vintage Soviet Lomo round-front anamorphic lenses, displaying pronounced swirly peripheral bokeh, chromatic edge fringing, and intense organic magenta-amber halation.`
* **ARRI Master Prime / Signature Prime（极致纯净数码透视）**：
  * *光学特征*：几乎零色散、零桶形畸变、从中心到边缘一致的刀锋锐度，高反差微对比极度扎实。
  * *H3 标准描述*：`Shot on ARRI Signature Prime lenses, offering razor-sharp optical purity, zero geometric distortion, immaculate chromatic aberration suppression, and smooth modern focus roll-off.`

### 2. 真实胶片感光乳剂基底（Film Stocks & Emulsion Physics）
* **Kodak Vision3 500T 5219（电影工业钨丝灯胶片基准）**：
  * *特征*：专为低照度与夜戏设计，细腻的卤化银颗粒结构（Fine Halide Grain），高光处拥有极宽容的柔和滚降（Highlight Roll-off），灯光边缘自然泛出橙红色光晕（Red Halation）。
  * *H3 标准描述*：`Photographed on 35mm Kodak Vision3 500T 5219 color negative stock, rendering authentic organic silver halide grain, natural orange-red halation blooms around practical lamps, and ultra-smooth creamy highlight roll-off.`
* **Kodak Vision3 250D 5207（自然日光型高保真胶片）**：
  * *特征*：色彩还原极其真实纯净，中灰阶丰富，天空与高反差日光下阴影细节极佳。
  * *H3 标准描述*：`Shot on 35mm Kodak Vision3 250D daylight film, featuring clean naturalistic color rendering, micro-fine grain texture, and expansive shadow latitude.`
* **Kodak Tri-X 400（经典高反差黑白胶片）**：
  * *特征*：粗粝扎实的银盐颗粒感，深邃坚硬的暗部（Crushed rich blacks），亮暗反差分明，极具纪实力量。
  * *H3 标准描述*：`35mm Kodak Tri-X 400 black-and-white film emulsion, characterized by gritty silver salt grain, dramatic high-contrast chiaroscuro, punchy mid-tone separation, and deep velvety blacks.`

### 3. 专业物理光学滤镜系统（Optical Filter Stacks）
* **Tiffen Black Pro-Mist 1/4（黑柔滤镜：消除数码锐利感）**：
  * *物理响应*：高光点产生柔和的漫反射光晕（Blooming），同时由于黑色微颗粒存在，完全保留了暗部的黑度和整体对比度，绝不发灰泛白。
  * *H3 标准描述*：`Utilizing 1/4 Tiffen Black Pro-Mist filter, delicately blooming intense highlight sources while preserving deep black floor contrast and softening skin micro-blemishes.`
* **Tiffen Glimmerglass 1（微光滤镜：清透与微闪光感）**：
  * *物理响应*：在保持整体极高通透感的同时，让演员的眼睛与高光点泛出微细优雅的闪烁感，暗部完全不雾化。
  * *H3 标准描述*：`Fitted with Tiffen Glimmerglass 1, creating crisp highlight sparkle in catchlights, subtle halation glow without shadow desaturation, and immaculate visual clarity.`
* **True-Net / Silk Stocking Diffusion（复古真丝/黑丝袜后置扩散）**：
  * *物理响应*：经典的黄金年代好莱坞手法，画面产生如油画般的星芒高光扩散与浪漫年代薄雾。
  * *H3 标准描述*：`Rear-element sheer black silk net diffusion, generating dreamy vintage starburst highlights, painterly optical softening, and romantic period film nostalgia.`

---

## 二、 世界院线级电影大师摄影与光影风格库

### 1. 罗杰·狄金斯风格（Roger Deakins Aesthetic - 极致自然主义与几何纯粹）
* **【风格基因】**：拒绝花哨炫技。坚持单一大面积自然光源动机（Motivated Light），极简克制；大反差但暗部绝不失真；精准的几何剪影（Silhouette）与极度纯净的透视。
* **【标准 H3 英文提示词原料】**：
  `Cinematic visual aesthetic in the masterful naturalistic tradition of Roger Deakins, captured with ARRI Master Primes for crystal optical fidelity. Characterized by motivated single-source architectural lighting, high-contrast chiaroscuro with immaculate shadow latitude, crisp geometric silhouettes framed against clean background gradients, and zero optical distortion.`

### 2. 维托里奥·斯托拉罗风格（Vittorio Storaro - 三基色对冲与潜意识心理光）
* **【风格基因】**：光影即哲学。极端强烈的色彩极性对抗（如：暴烈的暖赭红 vs 冰冷的深青蓝）；Technovision 变形宽银幕的大气恢弘；光线直接参与人物灵魂的审判。
* **【标准 H3 英文提示词原料】**：
  `Visual cinematography inspired by Vittorio Storaro, featuring dramatic symbolic color scripting. High-contrast illumination pits saturated 2600K amber-ochre tungsten against piercing 6500K deep cyan twilight, framed in 2.39:1 Technovision anamorphic scope with operatic shadow density and rich emotional color saturation.`

### 3. 王家卫 & 杜可风风格（Christopher Doyle & Wong Kar-wai - 抽帧拖影与迷离热病）
* **【风格基因】**：Step-printing（6~12 帧/秒拍摄再逐帧冲印）带来的梦幻拖影与动态模糊；高饱和荧光冷绿、腐蚀明黄与深绯红的病态对撞；极端广角贴身近距拍摄，制造极度拥挤与疏离并存的情感窒息感。
* **【标准 H3 英文提示词原料】**：
  `Fever-dream Hong Kong cinema aesthetic in the iconic style of Christopher Doyle and Wong Kar-wai, shot on 35mm film with authentic 8-12 fps step-printing shutter drag creating luminous motion trails. Dominated by saturated bilious fluorescent green and bruised amber-yellow color grading, extreme wide-angle claustrophobic close-ups, and 1/2 Black Pro-Mist optical halation blooming.`

### 4. 丹尼斯·维伦纽瓦 & 格雷格·弗莱瑟（Greig Fraser - 沙丘式巨构与极简大地哑光）
* **【风格基因】**：绝对的宏大与肃穆。大面积未被填满的负空间（Negative Space）；无反光的哑光微表面材质；弥漫在空气中的微细沙尘与颗粒漫反射（Airborne Atmospheric Particulate）；低饱和度的大地色谱（赭石、沙黄、灰黑）。
* **【标准 H3 英文提示词原料】**：
  `Monumental minimalist sci-fi cinematography directed in the visual scale of Greig Fraser and Denis Villeneuve. Photographed with ultra-large format spherical sensors, displaying desaturated monochromatic ochre and chalk-grey color palettes, vast negative space, soft volumetric dust diffusion scattering ambient desert sunlight, and non-reflective matte material surfaces.`

### 5. 90年代徐克/程小东经典港产武侠（Tsui Hark & Ching Siu-tung - 刀剑热血与胶片反差）
* **【风格基因】**：柯达 35mm 胶片颗粒；高速动作中的抽帧残影与大广角贴地仰冲；极高反差的烛火（2800K）与窗外夜雨闪电（6500K）卡拉瓦乔式剧烈冲撞；刀光剑影扫过镜头边缘造成的横向光斑。
* **【标准 H3 英文提示词原料】**：
  `1990s Hong Kong wuxia cinematic aesthetic in the kinetic tradition of Tsui Hark and Ching Siu-tung, shot on 35mm celluloid film with fine organic grain and 2.39:1 scope. High-contrast chiaroscuro lighting balances warm 2800K lantern glow against cold 6500K stormy cyan lightning flashes, accented by dynamic low-angle wide-angle camera dollies, blade glint reflections, and snappy physical impacts.`

### 6. 大卫·芬奇 & 杰夫·克罗宁威斯（David Fincher - 低照度数码冷冽与黄绿病理调色）
* **【风格基因】**：病态而精准的冷调。全片统治性的橄榄绿、脏黄与冷灰；8:1 极端低调光比（Low-key）；精准到毫米的平滑摄影机运动；暗部坚实且绝无一丝杂色。
* **【标准 H3 英文提示词原料】**：
  `Clinical neo-noir aesthetic directed in the razor-sharp visual discipline of David Fincher and Jeff Cronenweth. Low-key 8:1 chiaroscuro lighting dominated by sickly olive-green and muted mustard-yellow cast, pristine digital camera stability, deep shadow separation without noise, and immaculate modern micro-contrast.`

---

## 三、 专业原画作画（Sakuga）与动画监督大师风格矩阵

当需要动画、二次元、漫改或 3渲2 影视时，以下原画大师的作画指纹能彻底击穿平庸的扁平纸片人质感：

### 1. 中村丰风格（Yutaka Nakamura - 骨头社神级打戏之王）
* **【作画指纹】**：
  * **Nakamura Debris（方块碎屑）**：物体破碎时，不产生碎末，而是炸出极其鲜明、具有三维立体翻滚透视的立方体碎块。
  * **Inverted Impact Frames（黑白负片冲击帧）**：在重击接触的一瞬间，画面剥离色彩，出现 1~2 帧纯黑白/负片极高反差闪光。
  * **Stepped Timing（一拍二顿挫律动）**：平时极度流畅，爆发时抽帧产生极其凌厉的顿挫力量感。
* **【标准 H3 英文提示词原料】**：
  `High-octane sakuga anime visual aesthetic in the dynamic traditions of Yutaka Nakamura, utilizing variable dry-brush line-weights with aggressive charcoal-ink contours. Motion stepping on-twos (12 fps within 24 fps timeline) with dynamic animated smear frames across high-velocity trajectories. Impact physics generate explosive cubic fragmentation debris (Nakamura blocks) tumbling in zero-gravity arcs, punctuated by a single-frame negative color inversion flash on physical contact.`

### 2. 矶光雄风格（Mitsuo Iso - 物理重力与写实流体之神）
* **【作画指纹】**：
  * **极度写实的物理重量**：角色奔跑落地时脚踝的承重弯折、衣服褶皱因惯性产生的滞后摆动。
  * **波形烟雾（Volumetric Fluid Smoke）**：爆炸烟雾不是简单的圆圈，而是呈现出极其复杂的流体力学翻滚与内聚形态。
* **【标准 H3 英文提示词原料】**：
  `Realistic hand-drawn sakuga animation aesthetic in the technical tradition of Mitsuo Iso, emphasizing genuine physical weight, inertia, and secondary cloth draping. Explosions and dust disperse into intricate volumetric fluid lobes with internal pressure curling, maintaining strict anatomical volume preservation across dynamic rotations.`

### 3. 今石洋之 & 吉成曜（Studio Trigger / 扳机社 - 几何狂飙与波普超平面）
* **【作画指纹】**：
  * **极限形变与极端透视**：拳头由近及远呈现出 3 倍于骨骼限制的大透视；锐利的三角形与多边形爆发特效。
  * **波普高饱和色块**：纯青、洋红、明黄的纯色冲撞，毫无渐变的干净硬边塞璐璐。
* **【标准 H3 英文提示词原料】**：
  `Hyper-stylized Trigger anime aesthetic in the explosive animation grammar of Hiroyuki Imaishi and Yoh Yoshinari. Features razor-sharp geometric line-art, extreme forced perspective stretching fists and blades along the Z-axis, vibrant pop-art chromatic saturation, and sharp angular cel-shading with zero gradient softness.`

### 4. 新海诚 & 审美写实摄影系（Makoto Shinkai - 真实光学散斑与边缘色散）
* **【作画指纹】**：
  * **真实光学散斑（Anamorphic Bokeh）**：背景光斑带有摄影机镜头特有的光圈多边形与柔焦晕染。
  * **边缘色散（Chromatic Aberration）**：在强逆光边缘呈现出真实红蓝/青紫边缘分离。
  * **多层空气透视**：极其华丽的丁达尔光束（God rays）与空气中漂浮的发光微尘（Sun motes）。
* **【标准 H3 英文提示词原料】**：
  `Luminous contemporary anime aesthetic in the photographic style of Makoto Shinkai, featuring authentic optical lens flares, circular aperture bokeh, and subtle chromatic aberration along backlit silhouettes. Multi-layered atmospheric perspective filled with drifting illuminated dust particles and dramatic golden hour volumetric light rays.`

### 5. WIT / MAPPA 粗炭笔硬派素描系（《进击的巨人》《咒术回战》）
* **【作画指纹】**：
  * **极粗外轮廓压感线**：带有粗糙炭笔质感（Rough Charcoal Linework）的边缘黑线。
  * **重度交叉排线阴影（Cross-hatching）**：在面部与肌肉暗部使用漫画式的交叉细密排线，营造极度的残忍与工业压迫感。
* **【标准 H3 英文提示词原料】**：
  `Grim, gritty anime aesthetic in the illustrative style of WIT Studio and MAPPA, featuring heavy, variable-weight rough pencil contour lines and dense cross-hatched facial shadows. Desaturated earth-tone color palettes emphasize tactile mud, metallic weapon wear, and raw visceral dramatic weight.`

---

## 四、 前沿数字媒介与顶级游戏视觉美学

### 1. 米哈游《崩坏：星穹铁道》/《原神》顶流 3渲2 电影感（HoYoverse NPR Cinematic）
* **【渲染特征】**：
  * **NPR 非真实感着色（Non-Photorealistic Rendering）**：平滑阶梯阴影分层（Stepped Shadow Bands），面部阴影经过特制 SDF 阈值平滑，绝不出现三维软件常见的脏黑三角面。
  * **动态自发光光晕线（Emissive Rim Highlights）**：在发丝与角色边缘附带一道清脆的 2~3 像素高亮描边。
  * **半写实材质贴图**：服装保有真实的丝绸反光、皮革压纹与金属镜面，但人物面部保持极致纯净。
* **【标准 H3 英文提示词原料】**：
  `Premium 3D anime cel-shaded cinematic aesthetic in the cutting-edge rendering style of HoYoverse (Honkai: Star Rail). Impeccable NPR toon-shading with stepped two-tone shadow bands, pristine smooth facial shading free of mesh artifacts, crisp illuminated outer edge rim-lighting, and high-fidelity micro-textures on silk brocades and brushed metallic armor trim.`

### 2. 虚幻引擎 5 次世代写实工业（UE5 Nanite/Lumen Cinematic Realism）
* **【渲染特征】**：
  * **微多边形微表面粗糙度（Micro-roughness）**：完全基于物理的表面漫反射（PBR），在光线掠射角呈现出极其精准的菲涅尔反射（Fresnel）。
  * **实时全局光漫反射反弹（Lumen Diffuse Bounce）**：阳光照在红色地毯上，会将极其柔和的微红环境光真实反弹到近处天花板与人物下巴上。
* **【标准 H3 英文提示词原料】**：
  `Hyper-realistic next-generation cinematic render powered by Unreal Engine 5 aesthetic standards. Fully motivated Lumen global illumination featuring multi-bounce diffuse color bleeding, physically accurate PBR surface micro-roughness, microscopic metal edge oxidation, and cinematic depth of field rendering genuine sensor optical falloff.`

### 3. 《赛博朋克 2077》/《边缘行者》新黑色霓虹（Cyberpunk Neo-Noir）
* **【渲染特征】**：
  * **雨夜湿沥青全反射**：地面布满积水，将上空的霓虹灯招牌倒影拉伸出垂直彩色反光柱。
  * **全息 UI 色差拉丝（Glitch & Chromatic Dispersion）**：空气中悬浮的全息图带有微弱的扫描线（Scanlines）与 RGB 像素分离。
* **【标准 H3 英文提示词原料】**：
  `Cyberpunk neo-noir aesthetic featuring wet asphalt pavement with sharp vertical reflections of vibrant magenta and electric cyan neon signage. Atmospheric low-hanging smog illuminated by flickering sodium-vapor streetlights, punctuated by floating holographic UI interfaces with delicate RGB chromatic aberration and CRT scanline noise.`

---

## 五、 物理材质微表面与 BRDF 光学响应解剖

扩散模型画不好材质，是因为 Prompt 里只有名词没有物理光路。在编写角色与场景时，强制调用以下**微表面响应解剖语句**：

### 1. 人体皮肤微表面（Subsurface Scattering & Epidermal Sheen）
* **物理光学机理**：光线射入半透明皮肤角质层后，在毛细血管中发生多次散射再穿出，在耳垂、鼻翼、手指骨关节处产生血红色的柔和次表面透光（SSS）；同时汗腺分泌的水脂薄膜在强光下产生微弱的各向同性镜面高光。
* **H3 注入语句**：
  `Skin exhibits lifelike subsurface scattering (SSS) with warm reddish-orange transmission visible along the thin cartilage of ear rims and nose bridges. A subtle micro-layer of perspiration produces soft specular highlights across cheekbones and temples without artificial oily plastic sheen.`

### 2. 生铁与冷锻钢（Cast Iron vs. Forged Steel BRDF）
* **物理光学机理**：生铁是高吸收、漫反射为主的粗糙哑光表面，高光面宽而暗淡；冷锻高碳钢刃口经过反复研磨，呈现为一条极其锐利、窄幅、伴随微细研磨横纹的各向异性高光带（Anisotropic Specular Streak）。
* **H3 注入语句**：
  `Cast-iron spade features a dark, light-absorbing rough matte surface with micro-pitting and oxidation. In sharp contrast, the hand-ground blade edge displays a razor-thin, brilliant anisotropic specular highlight running along the whetstone grind lines.`

### 3. 古法织物：粗麻布与重工丝绸（Coarse Linen vs. Heavy Silk）
* **物理光学机理**：粗麻布纤维外露，高光极低，但在边缘逆光时会因表面微小毛羽产生一圈绒毛发光晕（Fabric Fuzz Rim Light）；重工丝绸具有极高的经纬交织各向异性，随着光线角度变动，产生流动的双色变幻光泽。
* **H3 注入语句**：
  `Faded indigo coarse linen robe displays dry, non-reflective weave textures with fine fibrous fuzz illuminated by rim-lighting along sleeve silhouettes. The crimson silk phoenix qipao gleams with directional anisotropic sheen, shifting from deep scarlet to brilliant spun-gold metallic reflection as the fabric drapes and flexes.`

### 4. 湿润介质与风化老木（Lacquered Elm vs. Boiling Broth）
* **物理光学机理**：百年老榆木由于长年浸润油脂与磨损，表层呈现出微弱的温润半光泽，木纹凹槽中填满深黑风化积灰；热汤表面由于油脂密度不同，漂浮的油圈呈现出折射率微小差异导致的同心圆彩虹色弱干涉光纹。
* **H3 注入语句**：
  `Aged elm tabletop displays a dark weathered patina with glossy rubbed wear along contact edges and matte dust in grain grooves. The steaming noodle broth features glistening golden oil rings on the amber surface, refracting subtle prismatic micro-highlights under warm lantern illumination.`

---

## 六、 即插即用的工业级万能质感组装公式

在编写任何 Segment 的 `detailed_description` 开头前 100 词时，按照以下 **四段式物理组装公式（The 4-Part Texture Stack）** 进行拼装：

$$\text{顶级质感开头} = \underbrace{\text{[光学镜头与银幕比例]}}_{\text{镜头畸变与光斑}} + \underbrace{\text{[感光胶片基底与滤镜栈]}}_{\text{颗粒感与高光柔和滚降}} + \underbrace{\text{[核心光色光比与介质]}}_{\text{主辅光比、色温冲突与体积空气}} + \underbrace{\text{[大师艺术监督画风指纹]}}_{\text{原画线条、形变律动与材质微表面}}$$

### 实战模板 1：90年代经典高燃港产武侠打戏（如《新龙门客栈》风格）
```text
Cinematic 1990s Hong Kong wuxia action aesthetic in the kinetic traditions of Tsui Hark and King Hu, captured on 35mm celluloid film using authentic Panavision C-series anamorphic prime lenses, 2.39:1 widescreen scope, and 1/4 Black Pro-Mist halation blooming around flickering flames. High-contrast chiaroscuro lighting pits warm 2800K lantern amber against cold 6500K stormy cyan lightning flashes. Dynamic hand-drawn sakuga animation line-weights accent explosive physical momentum, blade flex, and heavy impacts with authentic Kodak Vision3 organic grain.
```

### 实战模板 2：骨头社中村丰风格神级动画原画打戏（如《咒术回战》《一拳超人》风格）
```text
High-octane sakuga anime visual aesthetic in the dynamic traditions of Yutaka Nakamura, utilizing variable dry-brush line-weights with aggressive charcoal-ink contours. Shot with virtual 24mm wide-angle anamorphic lenses on stepped on-twos timing (12 fps within 24 fps timeline). Impact physics generate explosive cubic fragmentation debris (Nakamura blocks) tumbling in zero-gravity arcs, punctuated by a single-frame negative color inversion flash on physical weapon contact, accompanied by sharp cel-shading and zero gradient blur.
```

### 实战模板 3：米哈游《崩坏：星穹铁道》次世代 3渲2 影视工业感
```text
Premium 3D anime cel-shaded cinematic aesthetic in the cutting-edge rendering style of HoYoverse (Honkai: Star Rail). Impeccable NPR toon-shading with stepped two-tone shadow bands, pristine smooth facial shading free of mesh artifacts, crisp illuminated outer edge rim-lighting, and high-fidelity micro-textures on silk brocades and brushed metallic armor trim. Captured with crisp virtual prime lenses, soft aperture circular bokeh, and clean digital color grading balancing radiant teal and deep royal purple.
```

### 实战模板 4：罗杰·狄金斯现代电影级自然主义硬派写实
```text
Masterful naturalistic cinematic aesthetic in the visual tradition of Roger Deakins, captured with ARRI Signature Prime lenses on full-frame sensors for crystal optical purity. Governed by single-source motivated architectural lighting with deep 8:1 chiaroscuro contrast, immaculate shadow separation without noise, crisp geometric silhouettes, and subtle atmospheric dust scattering the beam path with zero optical distortion.
```
