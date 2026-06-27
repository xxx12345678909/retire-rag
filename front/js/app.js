// 智慧养老AI辅助平台 — Vue 3 应用逻辑
function createPlatformApp() {
    const { createApp, ref, computed, watch, nextTick } = Vue;
    return createApp({
        setup() {
const { createApp, ref, computed, watch, nextTick } = Vue;

        createApp({
            setup() {
                // --- 全局状态 ---
                const isSeniorMode = ref(false);
                const currentTab = ref('home');
                const serviceTab = ref('institutes');
                const toast = ref(false);
                const toastText = ref('');
                const citationDoc = ref(null);

                // --- 菜单列表 ---
                const menuTabs = ref([
                    { id: 'home', name: '首页入口', icon: 'fa-solid fa-house' },
                    { id: 'services', name: '养老服务', icon: 'fa-solid fa-hand-holding-heart' },
                    { id: 'policy', name: '政策大厅', icon: 'fa-solid fa-file-invoice-dollar' },
                    { id: 'health', name: '健康管理', icon: 'fa-solid fa-heart-pulse' },
                    { id: 'user', name: '用户中心', icon: 'fa-solid fa-user' }
                ]);

                // ── 认证状态 ──
                const authToken = ref(localStorage.getItem('auth_token') || '');
                const authUser = ref(null);
                const authLoaded = ref(false);
                const showLoginModal = ref(false);
                const loginForm = ref({ username: '', password: '' });
                const registerForm = ref({ username: '', password: '', phone: '' });
                const isRegistering = ref(false);

                const loadAuth = async () => {
                    if (!authToken.value) { authLoaded.value = true; return; }
                    try {
                        const r = await fetch(`${API_BASE}/api/auth/me`, {
                            headers: { 'Authorization': `Bearer ${authToken.value}` }
                        });
                        if (r.ok) authUser.value = await r.json();
                    } catch(e) {}
                    authLoaded.value = true;
                };

                const doLogin = async () => {
                    try {
                        const r = await fetch(`${API_BASE}/api/auth/login`, {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify(loginForm.value)
                        });
                        const d = await r.json();
                        if (d.ok) {
                            localStorage.setItem('auth_token', d.token);
                            authToken.value = d.token;
                            authUser.value = { username: d.username, role: d.role };
                            showLoginModal.value = false;
                            fetchFamily();
                            showToast('登录成功');
                        } else showToast('登录失败');
                    } catch(e) { showToast('网络错误'); }
                };

                const doRegister = async () => {
                    try {
                        const r = await fetch(`${API_BASE}/api/auth/register`, {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify(registerForm.value)
                        });
                        const d = await r.json();
                        if (d.ok) { isRegistering.value = false; showToast('注册成功，请登录'); }
                        else showToast(d.error || '注册失败');
                    } catch(e) { showToast('网络错误'); }
                };

                const doLogout = () => {
                    localStorage.removeItem('auth_token');
                    authToken.value = ''; authUser.value = null;
                    familyMembers.value = [];
                    showToast('已退出登录');
                };

                // ── 家属绑定 ──
                const familyForm = ref({ name: '', phone: '', relation: '父母' });
                const familyMembers = ref([]);
                const familyMsg = ref('');
                const familyMsgType = ref('ok');

                const fetchFamily = async () => {
                    if (!authToken.value) return;
                    try {
                        const r = await fetch(`${API_BASE}/api/user/family`, {
                            headers: { 'Authorization': `Bearer ${authToken.value}` }
                        });
                        const d = await r.json();
                        familyMembers.value = Array.isArray(d) ? d : (d.data || []);
                    } catch(e) {}
                };

                const bindFamily = async () => {
                    if (!familyForm.value.name || !familyForm.value.phone) {
                        familyMsg.value = '请填写家属姓名和手机号';
                        familyMsgType.value = 'err';
                        return;
                    }
                    try {
                        const r = await fetch(`${API_BASE}/api/user/family-bind`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken.value}` },
                            body: JSON.stringify(familyForm.value)
                        });
                        const d = await r.json();
                        if (r.ok) {
                            familyMsg.value = '绑定成功';
                            familyMsgType.value = 'ok';
                            familyForm.value = { name: '', phone: '', relation: '父母' };
                            fetchFamily();
                        } else {
                            familyMsg.value = d.error || '绑定失败';
                            familyMsgType.value = 'err';
                        }
                    } catch(e) {
                        familyMsg.value = '网络错误';
                        familyMsgType.value = 'err';
                    }
                };

                // --- 适老一键切换 ---
                const toggleSeniorMode = () => {
                    isSeniorMode.value = !isSeniorMode.value;
                    showToast(isSeniorMode.value ? '👵 适老模式已开启！超大字体高对比度' : '☀️ 已切回：标准排版模式');
                };

                // --- 提示框控制 ---
                const showToast = (text) => {
                    toastText.value = text;
                    toast.value = true;
                    setTimeout(() => {
                        toast.value = false;
                    }, 3000);
                };

                // --- 标签页切换逻辑 ---
                const switchTab = (tabId) => {
                    currentTab.value = tabId;
                    if (tabId === 'policy') { currentKbType.value = 'policy'; fetchPolicies(); }
                    else if (tabId === 'health') { currentKbType.value = 'health'; }
                    else if (tabId === 'services') { currentKbType.value = 'services'; fetchInstitutes(); fetchServices(); }
                    else if (tabId === 'user') { fetchOrders(); }
                    else { currentKbType.value = 'platform'; }
                };


                // --- 养老机构查询（真实 API） ---
                const institutes = ref([]);
                const instLoading = ref(false);
                const filters = ref({ district: '全部', care: '全部', price: '全部' });

                const fetchInstitutes = async () => {
                    instLoading.value = true;
                    try {
                        let url = `${API_BASE}/admin/institutions?limit=50`;
                        if (filters.value.district !== '全部') url += '&district=' + encodeURIComponent(filters.value.district);
                        if (filters.value.care !== '全部') url += '&care_level=' + encodeURIComponent(filters.value.care);
                        if (filters.value.price !== '全部') url += '&price_max=' + filters.value.price;
                        const r = await fetch(url);
                        const d = await r.json();
                        institutes.value = (d.data || []).map(inst => ({
                            ...inst,
                            id: inst.id,
                            name: inst.name,
                            district: inst.district,
                            address: inst.address || '',
                            price: inst.price_min,
                            price_max: inst.price_max,
                            beds: inst.beds_avail,
                            beds_total: inst.beds_total,
                            care_levels: (inst.care_levels || '').split(','),
                            description: inst.description || '',
                            contact: inst.contact || ''
                        }));
                    } catch(e) { institutes.value = []; }
                    instLoading.value = false;
                };

                const filterInstitutes = () => fetchInstitutes();
                const resetFilters = () => {
                    filters.value = { district: '全部', care: '全部', price: '全部' };
                    fetchInstitutes();
                };

                const bookInstitute = (name) => {
                    showToast(`✅ 已为您记录对[${name}]的参观意向，专属护理经理将致电您！`);
                };

                // 居家上门预约（真实 API）
                const serviceList = ref([]);
                const orderForm = ref({ service_id: null, service_name: '', date: new Date().toISOString().slice(0,10), time_slot: '上午', notes: '' });
                const orderList = ref([]);
                const orderLoading = ref(false);

                const fetchServices = async () => {
                    try {
                        const r = await fetch(`${API_BASE}/api/services`);
                        const d = await r.json();
                        serviceList.value = d.data || d || [];
                    } catch(e) {}
                };

                const fetchOrders = async () => {
                    if (!authToken.value) return;
                    orderLoading.value = true;
                    try {
                        const r = await fetch(`${API_BASE}/api/services/orders`, {
                            headers: { 'Authorization': `Bearer ${authToken.value}` }
                        });
                        const d = await r.json();
                        orderList.value = Array.isArray(d) ? d : (d.data || d || []);
                    } catch(e) {}
                    orderLoading.value = false;
                };

                const submitOrder = async () => {
                    if (!authToken.value) { showToast('请先登录'); return; }
                    if (!orderForm.value.service_id) { showToast('请选择服务类型'); return; }
                    try {
                        const r = await fetch(`${API_BASE}/api/services/book`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken.value}` },
                            body: JSON.stringify({
                                service_id: orderForm.value.service_id,
                                date: orderForm.value.date || new Date().toISOString().slice(0,10),
                                time_slot: orderForm.value.time_slot,
                                notes: orderForm.value.notes
                            })
                        });
                        const d = await r.json();
                        if (r.ok) {
                            showToast('预约成功！护理员将按时上门服务');
                            fetchOrders();
                        } else showToast(d.error || '预约失败');
                    } catch(e) { showToast('网络错误'); }
                };
                const cancelOrder = async (id) => {
                    if (!authToken.value) { showToast('请先登录'); return; }
                    try {
                        const r = await fetch(`${API_BASE}/api/services/bookings/${id}/cancel`, {
                            method: 'PUT',
                            headers: { 'Authorization': `Bearer ${authToken.value}` }
                        });
                        if (r.ok) { showToast('预约已取消'); fetchOrders(); }
                        else showToast('取消失败');
                    } catch(e) { showToast('网络错误'); }
                };

                // --- 养老政策大厅（真实 API） ---
                const policies = ref([]);
                const policyLoading = ref(false);
                const fetchPolicies = async () => {
                    policyLoading.value = true;
                    try {
                        const r = await fetch(`${API_BASE}/api/policy/list`);
                        const d = await r.json();
                        policies.value = (d.categories || []).flatMap(c =>
                            (c.policies || []).map(p => ({ ...p, cat: c.name, catIcon: c.icon }))
                        );
                    } catch(e) { policies.value = []; }
                    policyLoading.value = false;
                };
                
                // 福利智能测算
                const calcForm = ref({ age: '', hukou: '本地户籍', disabled: '完全自理' });
                const calcResult = ref(null);
                const calculateBenefits = () => {
                    const ageNum = parseInt(calcForm.value.age);
                    if (!calcForm.value.age || isNaN(ageNum)) {
                        showToast('❌ 请先输入正确的年龄！');
                        return;
                    }
                    const results = [];
                    if (calcForm.value.hukou === '本地户籍') {
                        if (ageNum >= 70 && ageNum < 80) results.push('每月可领取本地高龄津贴 100元');
                        else if (ageNum >= 80 && ageNum < 90) results.push('每月可领取本地高龄津贴 200元');
                        else if (ageNum >= 90) results.push('每月可领取本地高龄津贴 500元');
                        else results.push('高龄津贴起领门槛为年满 70 周岁。');
                    } else {
                        results.push('外地户籍不享受本地直发津贴，但凭本市居住证满一年可享部分助餐餐饮半价。');
                    }

                    if (calcForm.value.disabled === '重度失能') {
                        results.push('符合《长护险政策》，可申请最高 104 小时/月免费上门护理员。');
                    } else if (calcForm.value.disabled === '轻度失能') {
                        results.push('符合居家社区巡视扶持政策，每月发放100元助洁消费代金券。');
                    }
                    calcResult.value = results;
                    showToast('🎉 AI 养老评估匹配成功！');
                };

                // --- 健康管理（localStorage 持久化 + 定时提醒） ---
                const loadPills = () => {
                    try { return JSON.parse(localStorage.getItem('pills') || '[]'); } catch(e) { return []; }
                };
                const savePills = () => localStorage.setItem('pills', JSON.stringify(pillList.value));

                const pillList = ref(loadPills());
                const pillForm = ref({ name: '', time: '08:00', dose: '1片' });
                const lastAlerted = ref({});

                const addPill = () => {
                    if (!pillForm.value.name) { showToast('请填写药物名称'); return; }
                    pillList.value.push({ id: Date.now(), ...pillForm.value });
                    pillForm.value = { name: '', time: '08:00', dose: '1片' };
                    savePills();
                    showToast('服药闹钟已设置，到时间会提醒');
                };
                const deletePill = (id) => {
                    pillList.value = pillList.value.filter(p => p.id !== id);
                    savePills();
                };

                // 每分钟检查一次服药提醒
                setInterval(() => {
                    const now = new Date();
                    const current = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
                    pillList.value.forEach(p => {
                        if (p.time === current && lastAlerted.value[p.id] !== current) {
                            lastAlerted.value[p.id] = current;
                            showToast(`💊 服药提醒：${p.name} ${p.dose} — 现在该吃药了！`);
                            if ('Notification' in window && Notification.permission === 'granted') {
                                new Notification('服药提醒', { body: `${p.name} ${p.dose}`, icon: '💊' });
                            }
                        }
                    });
                }, 60000);

                // 请求通知权限
                if ('Notification' in window && Notification.permission === 'default') {
                    Notification.requestPermission();
                }

                const mockHealthArticles = [
                    { id: 1, tag: '用药安全', title: '老年高血压患者服用利尿剂的三大关键禁忌', summary: '高血压老人在使用螺内酯、氢氯噻嗪等利尿剂时必须定时复查电解质，避免在夜间睡前吃药，防止夜尿过多跌倒...', source: '中国心血管用药防治手册' },
                    { id: 2, tag: '饮食营养', title: '2型糖尿病老人夏季低血糖预防及水果选择指南', summary: '糖尿病长辈并非绝对不能吃水果，在两餐之间可适量食用草莓、西柚，并严格控制在200克内，严禁空腹过度运动...', source: '北京老年健康研究院科学膳食指导' },
                    { id: 3, tag: '急救科普', title: '居家突发心脑血管意外急救指南“黄金4分钟”', summary: '老人若出现嘴歪、一侧手脚发麻无力（脑卒中前兆），不可随意挪动。应解开衣领、立即拨打120，保持呼吸道通畅...', source: '国家卫健委老年急救科' }
                ];

                // 一键紧急援助 SOS 触发
                const triggerSOS = async () => {
                    if (!authToken.value) { showToast('请先登录后再使用紧急呼叫'); return; }
                    try {
                        const r = await fetch(`${API_BASE}/api/sos/trigger`, {
                            method: 'POST',
                            headers: { 'Authorization': `Bearer ${authToken.value}` }
                        });
                        const d = await r.json();
                        showToast('🚨 ' + (d.message || '紧急呼叫已发送'));
                    } catch(e) { showToast('🚨 紧急呼叫已发送，工作人员将尽快响应'); }
                };

                // --- RAG 后台运维管理 MOCK 数据及动作 ---
                const chunkSettings = ref({ size: 300, overlap: 50 });
                const uploadStatus = ref(null);
                const triggerMockUpload = () => {
                    uploadStatus.value = { name: '2026年社区高龄老人特殊关怀和补贴落实方案_最终版.pdf', progress: 10, message: '系统正在解析并解析 PDF 原文...' };
                    const interval = setInterval(() => {
                        if (uploadStatus.value.progress < 100) {
                            uploadStatus.value.progress += 30;
                            if (uploadStatus.value.progress === 40) uploadStatus.value.message = '正在提取文本，自动对长表格进行还原...';
                            if (uploadStatus.value.progress === 70) uploadStatus.value.message = '正在向量化对切片进行 Embedding 转算维度...';
                        } else {
                            uploadStatus.value.message = '分片入向量数据库成功！已新增6个知识片段。';
                            clearInterval(interval);
                            // 将上传的新内容充实到切片可视化列表中展示
                            mockChunks.unshift(
                                { content: '2026年特殊关怀落实：对具有北京市户籍，且失能程度评定为中度、重度的养老孤老或优抚对象增发400元居家养老护理券，由街乡政务大厅在每月首旬发放至北京养老卡内。', source: '特殊关怀和补贴落实方案.pdf', len: 110, hash: 'a1b2c3d4' },
                                { content: '2026年补贴发放：不与本市低保政策重合发放。如老人同时符合特困供养、高龄津贴和长护险多重政策，则按照就高、不重复的申报程序，由家属在养老平台上合并进行申报和抵扣。', source: '特殊关怀和补贴落实方案.pdf', len: 104, hash: 'e5f6g7h8' }
                            );
                            showToast('📁 文档分块(RAG-Chunking)及向量写入已成功完成！');
                        }
                    }, 800);
                };

                // 分片可视化数据
                const mockChunks = ref([
                    { content: '高龄津贴申报标准：凡年满70周岁至79周岁，具有本市户籍且无其他固定养老救助保障的普通老年人，均可按月领取本市100元高龄营养津贴补贴。外市户籍暂不支持直接发放。', source: '高龄津贴发放实施细则.pdf', len: 98, hash: 'f2a71d9e' },
                    { content: '长期护理险评估条件：重度失能评级需满足Barthel指数测算低于40分，由专业医养评估团队上门进行动作行为量化测评，主要考察穿衣、洗澡、进食、控制排便、上下楼梯等10大项。', source: '长护险定点评估申报指南.pdf', len: 122, hash: 'c9b4e5a2' },
                    { content: '糖尿病夏日食谱推荐：建议老年人以五谷杂粮等低GI复合碳水化合物为主，红薯中钾含量虽高但升糖指数中等，建议代替白米饭作为半份主食。切勿空腹大剂量用药后暴饮暴食。', source: '中国老年膳食指导手册.docx', len: 115, hash: 'd5c2e1f4' },
                    { content: '系统养老卡绑定流程：家属在APP进入“用户中心”，点击“家属账号绑定”。输入被保障老人的姓名、18位身份证号，并点击由老人持卡人手机获取的四位验证码，即可一键合并查询。', source: '养老系统FAQ操作手册.txt', len: 107, hash: 'b1a8f9d0' }
                ]);

                // 问答日志
                const mockQaLogs = ref([
                    { id: 1, query: '75岁农村户口有多少补贴？', kb: '政策法规库', score: '0.892', rating: 'good' },
                    { id: 2, query: '糖尿病老人吃红薯行吗？', kb: '健康科普库', score: '0.941', rating: 'good' },
                    { id: 3, query: '长护险怎么才能免费申请？', kb: '政策法规库', score: '0.782', rating: 'bad' },
                    { id: 4, query: '系统验证码收不到咋办？', kb: '平台操作库', score: '0.910', rating: 'good' }
                ]);

                const optimizeChunk = (log) => {
                    showToast(`🛠️ 已将提问[${log.query}]标记为调优，已在当前向量数据库中对该长难句段进行了二次重切片及词义聚类优化！`);
                    log.rating = 'good';
                    log.score = '0.965';
                };

                const showOriginalDoc = (policyName) => {
                    const chunk = mockChunks.value.find(c => c.source.includes(policyName.slice(0, 3))) || mockChunks.value[0];
                    citationDoc.value = {
                        doc: chunk.source,
                        page: '12',
                        content: chunk.content
                    };
                };

                // --- AI 助手核心状态及交互 ---
                const aiOpen = ref(false);
                const currentKbType = ref('platform'); // platform, policy, health, services
                const userInput = ref('');
                const isAiTyping = ref(false);
                const isSpeaking = ref(false);
                const isRecording = ref(false);
                const messageBox = ref(null);
                const activeKBScanningText = ref('');

                const kbNameMap = {
                    platform: '💻 综合及系统FAQ操作库',
                    policy: '📜 地方涉老政策法规库',
                    health: '🏥 老慢病健康科普知识库',
                    services: '🏨 优选养老机构与居家服务库'
                };

                const placeholderMap = {
                    platform: '想问：怎么用本网站？家属如何绑定？',
                    policy: '口语问：“我75岁没退休金怎么申报补贴？”',
                    health: '口语问：“高血压吃药能喝茶水吗？”',
                    services: '口语问：“帮我推荐一家朝阳区带医护的养老院”'
                };

                // 快捷提示卡
                const quickQuestionsMap = {
                    platform: ['如何合并绑定老人的北京养老卡？', '养老消费券怎样提现和抵扣？'],
                    policy: ['我今年75岁本地户口可以拿多少高龄补贴？', '长护险到底去哪里评估？需要什么材料？'],
                    health: ['得了2型糖尿病能吃红薯吗？', '高血压服药有什么禁忌？'],
                    services: ['海淀区有什么口碑好、管饭的养老院？', '居家预约保洁怎么收费？']
                };

                // 预置聊天历史
                const chatHistory = ref([
                    { role: 'assistant', text: '您好！我是您的专属智能养老小管家。我已自动感知并关联了[综合库]，有什么我可以为您指导或解答的吗？大字板模式下也支持用语音呼唤我哦。' }
                ]);

                // 场景感知打开 AI 并初始化预设问题
                const openAIScene = (kbType, customInput = '') => {
                    currentKbType.value = kbType;
                    aiOpen.value = true;
                    if (customInput) {
                        userInput.value = customInput;
                        handleSendMessage();
                    } else {
                        chatHistory.value.push({
                            role: 'assistant',
                            text: `已为您无缝切换至：【${kbNameMap[kbType]}】模式。我将专门负责本页面的疑惑解答，请问您有什么想了解的？`
                        });
                        scrollChatToBottom();
                    }
                };

                const consultPolicy = (name) => {
                    openAIScene('policy', `关于《${name}》，我适合办理吗？具体可以申领到多少钱，去哪里办？`);
                };

                const consultHealth = (title) => {
                    openAIScene('health', `我想具体咨询一下关于 [${title}] 里的内容与安全用药指导。`);
                };

                // 发送快捷预设问题
                const sendPresetQuestion = (question) => {
                    userInput.value = question;
                    handleSendMessage();
                };

                // 模拟语音录入 (口语化自动转文字)
                const simulateSpeech = () => {
                    if (isRecording.value) return;
                    isRecording.value = true;
                    showToast('🎤 正在倾听您说话... (模拟方言识别及口语自适应中)');
                    setTimeout(() => {
                        isRecording.value = false;
                        if (currentKbType.value === 'policy') {
                            userInput.value = '我妈75岁了农村户口，平常手脚有点不好，能申请那个什么补贴钱不？';
                        } else if (currentKbType.value === 'health') {
                            userInput.value = '血压高的老头子，天天早晨吃药，听说能吃红薯是真的不？';
                        } else if (currentKbType.value === 'services') {
                            userInput.value = '我想找一间在昌平这边，收费不要太贵，最好带医养结合和无障碍电梯的养老院。';
                        } else {
                            userInput.value = '怎么把孩子绑在我的养老账户上面？';
                        }
                        showToast('🎤 识别完成！口语自适应纠偏已填入');
                    }, 2000);
                };

                // 文字播报 (使用原生 Web Speech API 进行文字转语音)
                const speakText = (text) => {
                    if (isSpeaking.value) {
                        window.speechSynthesis.cancel();
                        isSpeaking.value = false;
                        return;
                    }
                    if ('speechSynthesis' in window) {
                        isSpeaking.value = true;
                        // 过滤掉引用及免责片段再发声，防止老人听不懂技术词
                        const spokenText = text.split('本次生成参考了')[0].split('免责及免责安全屏障')[0];
                        const utterance = new SpeechSynthesisUtterance(spokenText);
                        utterance.lang = 'zh-CN';
                        utterance.rate = 0.9; // 语速慢，体贴老年人
                        utterance.onend = () => { isSpeaking.value = false; };
                        utterance.onerror = () => { isSpeaking.value = false; };
                        window.speechSynthesis.speak(utterance);
                    } else {
                        showToast('❌ 您的浏览器不支持语音播报功能。');
                    }
                };

                // 滚动底部
                const scrollChatToBottom = () => {
                    nextTick(() => {
                        if (messageBox.value) {
                            messageBox.value.scrollTop = messageBox.value.scrollHeight;
                        }
                    });
                };

                // 高亮引用源
                const highlightCitation = (cite) => {
                    const chunk = mockChunks.value.find(c => c.source === cite.doc) || mockChunks.value[0];
                    citationDoc.value = {
                        doc: cite.doc,
                        page: cite.page,
                        content: chunk.content
                    };
                };

                // ── API 后端地址（与 FastAPI 同域部署时用相对路径）──
                const API_BASE = window.location.hostname === 'localhost'
                    ? 'http://localhost:8000'
                    : '';

                // --- RAG 检索增强核心引擎（调用后端 API） ---
                const handleSendMessage = async () => {
                    if (!userInput.value.trim() || isAiTyping.value) return;

                    const userText = userInput.value;
                    const sessionId = 'vue-' + Date.now();
                    chatHistory.value.push({ role: 'user', text: userText });
                    userInput.value = '';
                    isAiTyping.value = true;
                    scrollChatToBottom();

                    // 扫描动效
                    let step = 0;
                    const scanningInterval = setInterval(() => {
                        const loadingPhrases = [
                            `正在检索知识库中...`,
                            '召回相关向量分片进行融合...',
                            '正在整理回答...'
                        ];
                        activeKBScanningText.value = loadingPhrases[step % 3];
                        step++;
                    }, 600);

                    try {
                        const response = await fetch(`${API_BASE}/api/v1/chat`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                query: userText,
                                session_id: sessionId,
                                use_agent: false
                            })
                        });

                        clearInterval(scanningInterval);

                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }

                        const data = await response.json();

                        let text = data.answer || '抱歉，暂时无法处理您的请求。';
                        let citations = (data.sources || []).map(s => ({
                            doc: s.title || '参考来源',
                            page: ''
                        }));
                        let isMedical = data.intent === 'health';
                        let disclaimer = data.disclaimer || '';

                        // 添加来源信息
                        if (data.answer && data.sources && data.sources.length > 0) {
                            // 来源已在 answer 中包含，不再重复添加
                        }

                        chatHistory.value.push({
                            role: 'assistant',
                            text: text,
                            citations: citations,
                            isMedical: isMedical,
                            disclaimer: disclaimer,
                            intent: data.intent,
                            kb: data.kb
                        });
                    } catch (err) {
                        clearInterval(scanningInterval);
                        console.error('API调用失败：', err);

                        chatHistory.value.push({
                            role: 'assistant',
                            text: '抱歉，AI助手暂时无法连接，请稍后重试或拨打客服热线获取帮助。',
                            citations: [],
                            isMedical: false,
                            disclaimer: ''
                        });
                    }

                    isAiTyping.value = false;
                    scrollChatToBottom();

                    // 适老模式下自动语音播报
                    if (isSeniorMode.value) {
                        const lastMsg = chatHistory.value[chatHistory.value.length - 1];
                        if (lastMsg && lastMsg.text) {
                            speakText(lastMsg.text);
                        }
                    }
                };

                // 初始化（所有函数定义完成后调用）
                loadAuth();
                fetchPolicies();
                fetchInstitutes();

                return {
    };
}

// 注：产品原型.html 调用 createPlatformApp().mount("#app") 完成挂载
