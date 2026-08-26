() => {
  const PLACEHOLDER_RE =
    /^(seçiniz|seçin|belirleyin|placeholder|search|ara)$/i;
  const PLACEHOLDER_SOFT_RE =
    /seçiniz|seçin|belirleyin|örneğin|örn\.|placeholder|listeye eklemek|sonuç bulunamadı|no elements found|list is empty/i;
  const DEFAULT_EXP = /^(en az|en fazla)$/i;

  const cleanText = (el) => {
    if (!el) return "";
    if (typeof el === "string") return el.replace(/\s+/g, " ").trim();
    const node = el.cloneNode(true);
    node
      .querySelectorAll(
        ".multiselect__tag-icon, .icon-info, .required-star, button, svg, i.material-icons, .ms-caret, .ms-arrow"
      )
      .forEach((n) => n.remove());
    return (node.textContent || "").replace(/\s+/g, " ").trim();
  };

  const uniq = (arr) => {
    const out = [];
    const seen = new Set();
    for (const raw of arr || []) {
      const s = String(raw || "").replace(/\s+/g, " ").trim();
      if (!s) continue;
      const key = s.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    return out;
  };

  const isJunk = (t) => {
    if (!t) return true;
    const s = t.replace(/\s+/g, " ").trim();
    if (!s) return true;
    if (s === "[]") return true;
    if (PLACEHOLDER_RE.test(s)) return true;
    if (PLACEHOLDER_SOFT_RE.test(s) && s.length < 80) return true;
    return false;
  };

  const q = (sel, root = document) => {
    try {
      return root.querySelector(sel);
    } catch (e) {
      return null;
    }
  };
  const qa = (sel, root = document) => {
    try {
      return [...root.querySelectorAll(sel)];
    } catch (e) {
      return [];
    }
  };

  const firstMatch = (selectors, root = document) => {
    for (const s of selectors) {
      const el = q(s, root);
      if (el) return el;
    }
    return null;
  };

  const vueValue = (el) => {
    if (!el) return [];
    const inst =
      el.__vue__ ||
      el.__vueParentComponent ||
      (el.__vue_app__ && el.__vue_app__._instance);
    if (!inst) return [];
    const raw =
      inst.value ??
      inst.modelValue ??
      inst.$data?.value ??
      inst.$props?.value ??
      inst.props?.modelValue ??
      inst.props?.value ??
      inst.setupState?.value ??
      inst.setupState?.modelValue;
    return normalizeVue(raw);
  };

  const normalizeVue = (raw) => {
    if (raw == null || raw === "" || raw === false) return [];
    const one = (v) => {
      if (v == null || v === "") return "";
      if (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
        return String(v);
      return (
        v.displayName ||
        v.label ||
        v.name ||
        v.text ||
        v.title ||
        (typeof v.value === "string" ? v.value : "") ||
        ""
      );
    };
    if (Array.isArray(raw)) return uniq(raw.map(one).filter(Boolean));
    const s = one(raw);
    return s ? [s] : [];
  };

  const readMultiselect = (wrapper) => {
    if (!wrapper) return [];
    const root = wrapper.classList?.contains("multiselect")
      ? wrapper
      : q(".multiselect", wrapper) || wrapper;

    const fromVue = vueValue(root);
    if (fromVue.length) return fromVue.filter((t) => !isJunk(t));

    const tags = qa(".multiselect__tag", root)
      .map((tag) => cleanText(q("span", tag) || tag))
      .filter((t) => t && !isJunk(t));
    if (tags.length) return uniq(tags);

    const single = cleanText(q(".multiselect__single", root));
    if (single && !isJunk(single)) return [single];

    const selected = qa(".multiselect__option--selected", root)
      .map(cleanText)
      .filter((t) => t && !isJunk(t));
    if (selected.length) return uniq(selected);

    const native = q("select", wrapper);
    if (native) {
      const opts = [...native.selectedOptions]
        .map((o) => (o.textContent || "").trim())
        .filter((t) => t && !isJunk(t));
      if (opts.length) return uniq(opts);
    }
    return [];
  };

  const findByLabel = (labels) => {
    const wanted = (Array.isArray(labels) ? labels : [labels]).map((s) =>
      s.toLowerCase().replace(/\s+/g, " ").trim()
    );
    const nodes = qa(
      "label, .sm.bold, .form-label, p.sm, p.sm.bold, .section-title, legend, .education-level-filter__title, .department-filter__title, .d-flex.align-items-center, .mb-2"
    );
    for (const node of nodes) {
      let t = cleanText(node).replace(/\*/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
      if (!t || t.length > 90) continue;
      const hit = wanted.some(
        (w) => t === w || t.startsWith(w) || t.endsWith(w) || t.includes(w)
      );
      if (!hit) continue;
      let box =
        node.closest(
          ".form-group, fieldset, .col, .input-wrapper, [class*='filter'], .mb-4, .mb-3, .mb-2, .row, .salary-info-component, .language-filter, .military-status, .driver-licence"
        ) || node.parentElement;
      if (!box) continue;
      if (!q(".multiselect, input, textarea, select, .trumbowyg-editor", box)) {
        const up = box.parentElement;
        if (up && q(".multiselect, input, textarea, select, .trumbowyg-editor", up)) box = up;
      }
      return box;
    }
    return null;
  };

  const ms = (selectors, labels) => {
    for (const s of selectors || []) {
      const el = q(s);
      const vals = readMultiselect(el);
      if (vals.length) return vals;
    }
    if (labels) {
      const box = findByLabel(labels);
      const vals = readMultiselect(box);
      if (vals.length) return vals;
    }
    return [];
  };

  const scalar = (arr) => (arr && arr.length ? arr[0] : "");

  const readInput = (selectors) => {
    for (const s of selectors) {
      const el = q(s);
      if (!el) continue;
      const v = (el.value || "").trim();
      if (v && v !== "[]") return v;
    }
    return "";
  };

  const checkboxByLabel = (snippets) => {
    const wanted = (Array.isArray(snippets) ? snippets : [snippets]).map((s) =>
      s.toLowerCase()
    );
    const nodes = qa(
      "label, p, span, .custom-control-label, .disabled-check-text, .pl-1"
    );
    for (const node of nodes) {
      const t = cleanText(node).toLowerCase();
      if (!t || t.length > 160) continue;
      if (!wanted.some((w) => t.includes(w))) continue;
      const box =
        node.closest(
          ".custom-checkbox, .custom-control, .checkbox-2, .checkbox-3, .input-wrapper, .d-flex, .row, .form-group, .explicit-consent-text, .show-position-col"
        ) || node.parentElement;
      const input =
        (box && q('input[type="checkbox"]', box)) ||
        q('input[type="checkbox"]', node);
      if (input) return !!(input.checked || input.hasAttribute("checked"));
    }
    return false;
  };

  const harvestVueJobModel = () => {
    const roots = [
      q("#app"),
      q(".new-jobpage"),
      q("[job-model]"),
      document.body,
    ].filter(Boolean);
    const seen = new Set();
    const stack = [];
    for (const el of roots) {
      if (el.__vue__) stack.push(el.__vue__);
      if (el.__vueParentComponent) stack.push(el.__vueParentComponent);
    }
    qa("[data-v-014508a2], [data-v-359368f2], .new-jobpage *").slice(0, 400).forEach((el) => {
      if (el.__vue__) stack.push(el.__vue__);
      if (el.__vueParentComponent) stack.push(el.__vueParentComponent);
    });
    while (stack.length) {
      const inst = stack.pop();
      if (!inst || seen.has(inst)) continue;
      seen.add(inst);
      const bags = [
        inst.$data,
        inst.$props,
        inst.props,
        inst.setupState,
        inst.ctx,
        inst.jobModel,
        inst.job,
      ];
      for (const bag of bags) {
        if (!bag || typeof bag !== "object") continue;
        const model = bag.jobModel || bag.job || bag.model || bag;
        if (model && (model.position || model.jobPosition || model.title || model.qualifications)) {
          return model;
        }
      }
      if (inst.$children) stack.push(...inst.$children);
      if (inst.$parent) stack.push(inst.$parent);
      if (inst.parent) stack.push(inst.parent);
      if (inst.subTree?.component) stack.push(inst.subTree.component);
    }
    return null;
  };

  const position = ms(
    ["#jobPosition", "#jobPositionFormGroup", '[name="Pozisyon"]', "#jobPositionFormInput"],
    ["Pozisyon"]
  );
  const jobTitle =
    readInput(["#titleFormInput", 'input[name="İlan Başlığı"]', "#title input"]) ||
    scalar(ms(["#title", "#titleFormGroup"], ["İlan Başlığı"]));
  const department = ms(
    ["#businessArea", "#businessAreaFormGroup", '[name="Departman"]'],
    ["Departman"]
  );
  const jobLocation = ms(
    ["#jobLocation", "#jobLocationFormGroup", '[name="Pozisyon İl veya İlçe"]'],
    ["Pozisyon İl veya İlçe", "Lokasyon"]
  );
  const workingType = ms(
    ['[name="workingTypeList"]', "#workingTypeList"],
    ["Çalışma Şekli"]
  );
  const remoteWorkType = ms(
    ['[name="remoteWorkType"]', "#remoteWorkType"],
    ["Çalışma Tercihi", "Çalışma Konumu"]
  );
  const isDisabledJob = checkboxByLabel([
    "yalnızca engelli adaylar",
    "engelli adaylar başvursun",
    "engelli ilanı",
  ]);
  const positionLevel = ms(
    ['[name="positionLevelList"]', "#positionLevelList"],
    ["Pozisyon Seviyesi"]
  );
  let minExperience = ms([".min-experience-wrapper"], ["Deneyim"]);
  let maxExperience = ms([".max-experience-wrapper"]);
  if (minExperience.length === 1 && DEFAULT_EXP.test(minExperience[0])) {
    /* keep displayed default */
  }
  const candidateLocation = ms(
    ["#candidateLocation", "#candidateLocationFormGroup"],
    ["Yaşadığı Yer"]
  );
  const educationLevel = ms(
    ["#educationLevel", "#educationLevelFormGroup"],
    ["Eğitim Seviyesi"]
  );
  const addUniversityRequest = checkboxByLabel([
    "üniversite bilgisi eklemek",
    "üniversite bilgisi",
  ]);
  const departmentRequirement = ms(
    ["#department", "#departmentFormGroup"],
    ["Bölüm"]
  );
  const foreignLanguage = ms(['[name="language"]'], ["Yabancı Dil"]);
  const languageLevel = ms(
    ['[name="languageLevel"]', "#language-level"],
    ["Dil Seviyesi"]
  );
  const militaryStatus = ms(
    ['[name="militaryStatus"]'],
    ["Askerlik Bilgisi"]
  );
  const driverLicence = ms(['[name="driverLicence"]'], ["Sürücü Belgesi"]);
  const skills = ms(["#keyword", "#keywordFormGroup", '[name="Yetenekler"]'], ["Yetenekler"]);
  const candidatePositions = ms(
    ["#applicantPosition", "#applicantPositionFormGroup"],
    ["Çalıştığı Pozisyon"]
  );
  const candidateSectors = ms(
    ["#applicantSector", "#applicantSectorFormGroup"],
    ["Çalıştığı Sektör"]
  );
  const hideSalaryFromCandidates = checkboxByLabel([
    "adayların görmesini istemiyorum",
    "bu bilgiyi adayların görmesini",
  ]);
  const salaryType = ms(
    [
      "#salaryType",
      '[aria-owns="listbox-salaryType"]',
      '[name="salaryType"]',
    ],
    ["Maaş Türü"]
  );
  const paymentFrequency = ms(
    [
      "#paymentFrequency",
      '[aria-owns="listbox-paymentFrequency"]',
      '[name="paymentFrequency"]',
    ],
    ["Ödeme Sıklığı"]
  );
  const minSalary = readInput([
    'input[placeholder="Minimum değer"]',
    'input[placeholder*="Minimum"]',
  ]);
  const maxSalary = readInput([
    'input[placeholder="Maksimum değer"]',
    'input[placeholder*="Maksimum"]',
  ]);
  const symbolEl = q(".input-symbol");
  const currency =
    minSalary || maxSalary ? cleanText(symbolEl) || "TL" : "";

  const editorEl = firstMatch([
    ".trumbowyg-editor",
    "#job_create_qualifications .trumbowyg-editor",
    '[contenteditable="true"]',
    "#job_create_qualificationsFormInput",
    'textarea[name="İş Tanımı ve Genel Nitelikler"]',
  ]);
  let jobDescriptionText = "";
  let jobDescriptionHtml = "";
  if (editorEl) {
    if (editorEl.tagName === "TEXTAREA" || editorEl.tagName === "INPUT") {
      jobDescriptionText = (editorEl.value || "").replace(/\s+/g, " ").trim();
      jobDescriptionHtml = editorEl.value || "";
    } else {
      jobDescriptionText = cleanText(editorEl);
      jobDescriptionHtml = editorEl.innerHTML || "";
    }
  }

  let jobImageUrl = "";
  const bgStyleEl = firstMatch([
    ".skin-job-images-wrapper",
    '.skin-job-images [style*="url"]',
    '[style*="jobtemplate"]',
  ]);
  if (bgStyleEl) {
    const st =
      bgStyleEl.getAttribute("style") ||
      getComputedStyle(bgStyleEl).backgroundImage ||
      "";
    const match = String(st).match(/url\(["']?(.*?)["']?\)/);
    if (match && match[1] && match[1] !== "none") jobImageUrl = match[1];
  }

  const selectedQuestions = qa(".question-item")
    .filter((item) => {
      const chk = q('input[type="checkbox"]', item);
      return chk && (chk.checked || chk.hasAttribute("checked"));
    })
    .map((item) => cleanText(q(".lg", item)))
    .filter(Boolean);

  const explicitConsentRequired = checkboxByLabel([
    "açık rıza onayı almak",
    "adaylardan açık rıza",
  ]);

  let automaticMessage = "";
  const selectedMessageEl = q(
    '.quick-messages-list-item input[type="radio"]:checked, .quick-messages-list-item input[type="radio"][checked]'
  );
  if (selectedMessageEl) {
    const titleEl = selectedMessageEl
      .closest(".quick-messages-list-item")
      ?.querySelector(".quick-messages-list-item-title");
    automaticMessage = cleanText(titleEl);
  }

  const referenceNumber = readInput([
    "#jobCodeFormInput",
    'input[name="Referans Numarası"]',
    "#jobCode input",
  ]);
  const companyProfile = ms(
    ["#companyProfiles", "#companyProfilesFormGroup", '[name="Şirket Sayfası"]'],
    ["Şirket Sayfası"]
  );

  const vueModel = harvestVueJobModel();

  return {
    pozisyon: scalar(position),
    ilan_basligi: jobTitle,
    departman: scalar(department),
    lokasyon: jobLocation,
    calisma_sekli: scalar(workingType),
    calisma_tercihi: scalar(remoteWorkType),
    engelli_ilani: isDisabledJob,
    pozisyon_seviyesi: scalar(positionLevel),
    min_deneyim: scalar(minExperience),
    max_deneyim: scalar(maxExperience),
    candidate_location: candidateLocation,
    egitim_seviyesi: educationLevel,
    uni_ekleme_istegi: addUniversityRequest,
    bolumler: departmentRequirement,
    yabanci_dil: foreignLanguage,
    dil_seviyesi: scalar(languageLevel),
    askerlik_bilgisi: militaryStatus,
    surucu_belgesi: driverLicence,
    yetenekler: skills,
    calistigi_pozisyonlar: candidatePositions,
    calistigi_sektorler: candidateSectors,
    adaylerden_gizle: hideSalaryFromCandidates,
    maas_turu: scalar(salaryType),
    odeme_sikligi: scalar(paymentFrequency),
    min_maas: minSalary,
    max_maas: maxSalary,
    para_birimi: currency,
    ilan_aciklamasi: jobDescriptionText,
    ilan_aciklamasi_html: jobDescriptionHtml,
    ilan_gorsel_url: jobImageUrl,
    secili_sorular: selectedQuestions,
    acik_riza_onayi: explicitConsentRequired,
    otomatik_mesaj: automaticMessage,
    referans_no: referenceNumber,
    sirket_sayfasi: scalar(companyProfile),
    _vue_model_found: !!vueModel,
  };
}