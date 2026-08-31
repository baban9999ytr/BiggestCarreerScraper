from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from playwright.async_api import Locator, Page

logger = logging.getLogger("automation_process_jobs")

TAB_ROUTES = {
    "include_active": "/ilanlarim/yayindakiler",
    "include_passive": "/ilanlarim/pasifler",
    "include_drafts": "/ilanlarim/taslaklar",
    "include_archived": "/ilanlarim/arsivlenmis",
}

JOB_TYPE_BY_ROUTE = {
    "/ilanlarim/yayindakiler": "active",
    "/ilanlarim/pasifler": "passive",
    "/ilanlarim/taslaklar": "draft",
    "/ilanlarim/arsivlenmis": "archived",
}

ATS_ORIGIN = "https://ats.kariyer.net"

_EXTRACT_CANDIDATES_MULTI_FALLBACK_JS = r"""
(maxCount) => {
    const cleanText = (el) => (el?.textContent || el?.innerText || '').replace(/\s+/g, ' ').trim();
    const cleanName = (str) => {
        let s = String(str || '').replace(/\s+/g, ' ').trim();
        s = s.replace(/,+\s*$/, '');
        s = s.replace(/,?\s*\d{1,2}(\s+.*)?$/, '').trim();
        s = s.replace(/,+$/, '').trim();
        return s;
    };
    const absUrl = (href) => {
        if (!href) return '';
        return String(href).replace(/&/g, '&').trim();
    };
    const readName = (root) => {
        if (!root) return '';
        const el = root.querySelector('b.fullname, .fullname-wrapper b, span.fullname');
        if (el) return cleanName(cleanText(el));
        const wrap = root.querySelector('.fullname-wrapper .lg, .fullname-wrapper');
        if (wrap) return cleanName(cleanText(wrap));
        return '';
    };
    const readTitle = (root) => {
        if (!root) return '';
        const employer = root.querySelector('.employer');
        if (employer) {
            const box = employer.closest('.card-width-limiter') || employer.parentElement;
            const bold = box && box.querySelector(':scope > .font-weight-bold, .font-weight-bold');
            if (bold) return cleanText(bold);
        }
        const webLines = [...root.querySelectorAll('.card-width-limiter.right-block-relative-web')];
        for (const line of webLines) {
            if (line.querySelector('.employer')) {
                return cleanText(line.querySelector('.font-weight-bold'));
            }
        }
        return '';
    };
    const readUrl = (node) => {
        const a = (node && node.closest && node.closest('a[href*="ozgecmis"]'))
            || (node && node.querySelector && node.querySelector('a[href*="ozgecmis"]'))
            || (node && node.closest && node.closest('a'))
            || (node && node.querySelector && node.querySelector('a'));
        return absUrl(a ? a.getAttribute('href') : '');
    };

    const seen = new Set();
    const out = [];
    const push = (item) => {
        const name = cleanName(item.name || '');
        const title = String(item.title || '').replace(/\s+/g, ' ').trim();
        const detail_url = absUrl(item.detail_url || '');
        if (!name) return;
        const key = (detail_url.split('?')[0] || name).toLowerCase();
        if (key && seen.has(key)) return;
        if (key) seen.add(key);
        out.push({ name, title, detail_url });
    };

    const cards = [...document.querySelectorAll('.resume-card, .candidate-card, .applicant-card')]
        .filter((el) => !/wrapper/i.test(el.className || '') && (el.querySelector('.fullname') || el.querySelector('.employer')));
    for (const c of cards) {
        push({ name: readName(c), title: readTitle(c), detail_url: readUrl(c) });
    }

    if (!out.length) {
        const anchors = [
            ...document.querySelectorAll('a[href*="/ozgecmis-detay/"], a[href*="/ozgecmis/"], a[href*="/aday/"]')
        ].filter((a) => a.querySelector('.fullname, .resume-card, .employer'));
        for (const a of anchors) {
            const card = a.querySelector('.resume-card') || a;
            push({
                name: readName(card) || readName(a),
                title: readTitle(card) || readTitle(a),
                detail_url: a.getAttribute('href') || ''
            });
        }
    }

    if (!out.length) {
        try {
            const vueRoots = [
                document.querySelector('#app'),
                document.querySelector('.applicant-list-page-container'),
                document.querySelector('.candidate-list-page-container'),
                document.body
            ].filter(Boolean);
            const seenInst = new Set();
            const stack = [];
            for (const el of vueRoots) {
                if (el.__vue__) stack.push(el.__vue__);
                if (el.__vueParentComponent) stack.push(el.__vueParentComponent);
            }
            while (stack.length) {
                const inst = stack.pop();
                if (!inst || seenInst.has(inst)) continue;
                seenInst.add(inst);
                const bags = [inst.$data, inst.$props, inst.props, inst.setupState, inst.ctx];
                for (const bag of bags) {
                    if (!bag || typeof bag !== 'object') continue;
                    const list = bag.candidates || bag.applicantList || bag.resumes
                        || bag.applications || bag.items || bag.resumeList || bag.cvList;
                    if (Array.isArray(list) && list.length > 0 && typeof list[0] === 'object') {
                        for (const item of list) {
                            const full = item.fullname || item.fullName || item.name
                                || item.candidateName || `${item.firstName || ''} ${item.lastName || ''}`;
                            push({
                                name: full,
                                title: item.title || item.jobTitle || item.positionTitle
                                    || item.lastPosition || item.position || '',
                                detail_url: item.detailUrl || item.href || item.url
                                    || item.resumeUrl || (item.id ? `/ozgecmis-detay/${item.id}` : '')
                            });
                        }
                        if (out.length) break;
                    }
                }
                if (out.length) break;
                if (inst.$children) stack.push(...inst.$children);
                if (inst.$parent) stack.push(inst.$parent);
                if (inst.parent) stack.push(inst.parent);
                if (inst.subTree?.component) stack.push(inst.subTree.component);
            }
        } catch (e) {}
    }

    if (typeof maxCount === 'number' && maxCount >= 0) return out.slice(0, maxCount);
    return out;
}
"""

_EXTRACT_WIZARD_JS = r"""
() => {
  const PLACEHOLDER_RE = /^(seçiniz|seçin|belirleyin|placeholder|search|ara)$/i;
  const PLACEHOLDER_SOFT_RE = /seçiniz|seçin|belirleyin|örneğin|örn\.|placeholder|listeye eklemek|sonuç bulunamadı|no elements found|list is empty/i;
  const DEFAULT_EXP = /^(en az|en fazla)$/i;

  const cleanText = (el) => {
    if (!el) return "";
    if (typeof el === "string") return el.replace(/\s+/g, " ").trim();
    const node = el.cloneNode(true);
    node.querySelectorAll(".multiselect__tag-icon, .icon-info, .required-star, button, svg, i.material-icons, .ms-caret, .ms-arrow").forEach((n) => n.remove());
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

  const q = (sel, root = document) => { try { return root.querySelector(sel); } catch (e) { return null; } };
  const qa = (sel, root = document) => { try { return [...root.querySelectorAll(sel)]; } catch (e) { return []; } };

  const firstMatch = (selectors, root = document) => {
    for (const s of selectors) {
      const el = q(s, root);
      if (el) return el;
    }
    return null;
  };

  const vueInst = (el) => {
    if (!el) return null;
    return el.__vue__ || el.__vueParentComponent || (el.__vue_app__ && el.__vue_app__._instance) || null;
  };

  const vueValue = (el) => {
    const inst = vueInst(el);
    if (!inst) return [];
    const raw = inst.value ?? inst.modelValue ?? inst.$data?.value ?? inst.$props?.value
      ?? inst.props?.modelValue ?? inst.props?.value ?? inst.setupState?.value
      ?? inst.setupState?.modelValue;
    return normalizeVue(raw);
  };

  const normalizeVue = (raw) => {
    if (raw == null || raw === "" || raw === false) return [];
    const one = (v) => {
      if (v == null || v === "") return "";
      if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
      return v.displayName || v.label || v.name || v.text || v.title || (typeof v.value === "string" ? v.value : "") || "";
    };
    if (Array.isArray(raw)) return uniq(raw.map(one).filter(Boolean));
    const s = one(raw);
    return s ? [s] : [];
  };

  const readMultiselect = (wrapper) => {
    if (!wrapper) return [];
    const root = wrapper.classList?.contains("multiselect") ? wrapper : q(".multiselect", wrapper) || wrapper;
    const fromVue = vueValue(root);
    if (fromVue.length) return fromVue.filter((t) => !isJunk(t));
    const tags = qa(".multiselect__tag", root).map((tag) => cleanText(q("span", tag) || tag)).filter((t) => t && !isJunk(t));
    if (tags.length) return uniq(tags);
    const single = cleanText(q(".multiselect__single", root));
    if (single && !isJunk(single)) return [single];
    const selected = qa(".multiselect__option--selected", root).map(cleanText).filter((t) => t && !isJunk(t));
    if (selected.length) return uniq(selected);
    const native = q("select", wrapper);
    if (native) {
      const opts = [...native.selectedOptions].map((o) => (o.textContent || "").trim()).filter((t) => t && !isJunk(t));
      if (opts.length) return uniq(opts);
    }
    return [];
  };

  const findByLabel = (labels) => {
    const wanted = (Array.isArray(labels) ? labels : [labels]).map((s) => s.toLowerCase().replace(/\s+/g, " ").trim());
    const nodes = qa("label, .sm.bold, .form-label, p.sm, p.sm.bold, .section-title, legend, .education-level-filter__title, .department-filter__title, .d-flex.align-items-center, .mb-2");
    for (const node of nodes) {
      let t = cleanText(node).replace(/\*/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
      if (!t || t.length > 90) continue;
      const hit = wanted.some((w) => t === w || t.startsWith(w) || t.endsWith(w) || t.includes(w));
      if (!hit) continue;
      let box = node.closest(".form-group, fieldset, .col, .input-wrapper, [class*='filter'], .mb-4, .mb-3, .mb-2, .row, .salary-info-component, .language-filter, .military-status, .driver-licence") || node.parentElement;
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
      let v = (el.value || el.getAttribute("value") || "").trim();
      if (!v) {
        const fromVue = vueValue(el);
        if (fromVue.length) v = fromVue[0];
      }
      if (v && v !== "[]" && !isJunk(v)) return v;
    }
    return "";
  };

  const checkboxByLabel = (snippets) => {
    const wanted = (Array.isArray(snippets) ? snippets : [snippets]).map((s) => s.toLowerCase());
    const nodes = qa("label, p, span, .custom-control-label, .disabled-check-text, .pl-1");
    for (const node of nodes) {
      const t = cleanText(node).toLowerCase();
      if (!t || t.length > 160) continue;
      if (!wanted.some((w) => t.includes(w))) continue;
      const box = node.closest(".custom-checkbox, .custom-control, .checkbox-2, .checkbox-3, .input-wrapper, .d-flex, .row, .form-group, .explicit-consent-text, .show-position-col") || node.parentElement;
      const input = (box && q('input[type="checkbox"]', box)) || q('input[type="checkbox"]', node);
      if (input) return !!(input.checked || input.hasAttribute("checked"));
    }
    return false;
  };

  const harvestVueJobModel = () => {
    const roots = [q("#app"), q(".new-jobpage"), q("[job-model]"), document.body].filter(Boolean);
    const seen = new Set();
    const stack = [];
    for (const el of roots) {
      if (el.__vue__) stack.push(el.__vue__);
      if (el.__vueParentComponent) stack.push(el.__vueParentComponent);
    }
    qa("[data-v-014508a2], [data-v-359368f2], .new-jobpage *").slice(0, 800).forEach((el) => {
      if (el.__vue__) stack.push(el.__vue__);
      if (el.__vueParentComponent) stack.push(el.__vueParentComponent);
    });
    let found = null;
    while (stack.length) {
      const inst = stack.pop();
      if (!inst || seen.has(inst)) continue;
      seen.add(inst);
      const bags = [inst.$data, inst.$props, inst.props, inst.setupState, inst.ctx, inst.jobModel, inst.job];
      for (const bag of bags) {
        if (!bag || typeof bag !== "object") continue;
        const model = bag.jobModel || bag.job || bag.model || bag;
        if (model && typeof model === "object" && (model.position || model.jobPosition || model.title || model.qualifications || model.jobCode || model.keywords)) {
          found = model;
          break;
        }
      }
      if (found) break;
      if (inst.$children) stack.push(...inst.$children);
      if (inst.$parent) stack.push(inst.$parent);
      if (inst.parent) stack.push(inst.parent);
      if (inst.subTree?.component) stack.push(inst.subTree.component);
    }
    return found;
  };

  const asText = (v) => {
    if (v == null || v === false) return "";
    if (typeof v === "string" || typeof v === "number") return String(v).trim();
    if (Array.isArray(v)) return "";
    return v.displayName || v.label || v.name || v.text || v.title || "";
  };
  const asList = (v) => {
    if (v == null || v === "") return [];
    if (Array.isArray(v)) return uniq(v.map((x) => asText(x) || (typeof x === "string" ? x : "")).filter((t) => t && !isJunk(t)));
    const s = asText(v);
    return s && !isJunk(s) ? [s] : [];
  };

  const position = ms(["#jobPosition", "#jobPositionFormGroup", '[name="Pozisyon"]', "#jobPositionFormInput"], ["Pozisyon"]);
  const jobTitle = readInput(["#titleFormInput", 'input[name="İlan Başlığı"]', "#title input"]) || scalar(ms(["#title", "#titleFormGroup"], ["İlan Başlığı"]));
  const department = ms(["#businessArea", "#businessAreaFormGroup", '[name="Departman"]'], ["Departman"]);
  const jobLocation = ms(["#jobLocation", "#jobLocationFormGroup", '[name="Pozisyon İl veya İlçe"]'], ["Pozisyon İl veya İlçe", "Lokasyon"]);
  const workingType = ms(['[name="workingTypeList"]', "#workingTypeList"], ["Çalışma Şekli"]);
  const remoteWorkType = ms(['[name="remoteWorkType"]', "#remoteWorkType"], ["Çalışma Tercihi", "Çalışma Konumu"]);
  const isDisabledJob = checkboxByLabel(["yalnızca engelli adaylar", "engelli adaylar başvursun", "engelli ilanı"]);
  const positionLevel = ms(['[name="positionLevelList"]', "#positionLevelList"], ["Pozisyon Seviyesi"]);
  let minExperience = ms([".min-experience-wrapper"], ["Deneyim"]);
  let maxExperience = ms([".max-experience-wrapper"]);
  if (minExperience.length === 1 && DEFAULT_EXP.test(minExperience[0])) {}

  const candidateLocation = ms(["#candidateLocation", "#candidateLocationFormGroup"], ["Yaşadığı Yer"]);
  const educationLevel = ms(["#educationLevel", "#educationLevelFormGroup"], ["Eğitim Seviyesi"]);
  const addUniversityRequest = checkboxByLabel(["üniversite bilgisi eklemek", "üniversite bilgisi"]);
  const departmentRequirement = ms(["#department", "#departmentFormGroup"], ["Bölüm"]);
  const foreignLanguage = ms(['[name="language"]'], ["Yabancı Dil"]);
  const languageLevel = ms(['[name="languageLevel"]', "#language-level"], ["Dil Seviyesi"]);
  const militaryStatus = ms(['[name="militaryStatus"]'], ["Askerlik Bilgisi"]);
  const driverLicence = ms(['[name="driverLicence"]'], ["Sürücü Belgesi"]);
  const skills = ms(["#keyword", "#keywordFormGroup", '[name="Yetenekler"]'], ["Yetenekler"]);
  const candidatePositions = ms(["#applicantPosition", "#applicantPositionFormGroup"], ["Çalıştığı Pozisyon"]);
  const candidateSectors = ms(["#applicantSector", "#applicantSectorFormGroup"], ["Çalıştığı Sektör"]);
  const hideSalaryFromCandidates = checkboxByLabel(["adayların görmesini istemiyorum", "bu bilgiyi adayların görmesini"]);
  const salaryType = ms(["#salaryType", '[aria-owns="listbox-salaryType"]', '[name="salaryType"]'], ["Maaş Türü"]);
  const paymentFrequency = ms(["#paymentFrequency", '[aria-owns="listbox-paymentFrequency"]', '[name="paymentFrequency"]'], ["Ödeme Sıklığı"]);
  const minSalary = readInput(['input[placeholder="Minimum değer"]', 'input[placeholder*="Minimum"]']);
  const maxSalary = readInput(['input[placeholder="Maksimum değer"]', 'input[placeholder*="Maksimum"]']);
  const symbolEl = q(".input-symbol");
  const currency = minSalary || maxSalary ? cleanText(symbolEl) || "TL" : "";

  const editorEl = firstMatch([".trumbowyg-editor", "#job_create_qualifications .trumbowyg-editor", '[contenteditable="true"]', "#job_create_qualificationsFormInput", 'textarea[name="İş Tanımı ve Genel Nitelikler"]']);
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
  const bgStyleEl = firstMatch([".skin-job-images-wrapper", '.skin-job-images [style*="url"]', '[style*="jobtemplate"]']);
  if (bgStyleEl) {
    const st = bgStyleEl.getAttribute("style") || getComputedStyle(bgStyleEl).backgroundImage || "";
    const match = String(st).match(/url\(["']?(.*?)["']?\)/);
    if (match && match[1] && match[1] !== "none") jobImageUrl = match[1];
  }

  const isChecked = (chk) => {
    if (!chk) return false;
    if (chk.checked || chk.hasAttribute("checked") || chk.getAttribute("aria-checked") === "true") return true;
    const inst = vueInst(chk);
    if (inst) {
      const raw = inst.checked ?? inst.$data?.checked ?? inst.modelValue ?? inst.value
        ?? inst.props?.checked ?? inst.$props?.checked;
      if (raw === true || raw === "true") return true;
    }
    return false;
  };

  const selectedQuestions = qa(".question-item").filter((item) => isChecked(q('input[type="checkbox"]', item)))
    .map((item) => cleanText(q(".lg", item))).filter(Boolean);

  const explicitConsentRequired = checkboxByLabel(["açık rıza onayı almak", "adaylardan açık rıza"]);

  let automaticMessage = "";
  const messageRadios = qa(".quick-messages-list-item input[type='radio']");
  const selectedMessageEl = messageRadios.find((r) => isChecked(r)) || q('.quick-messages-list-item input[type="radio"]:checked, .quick-messages-list-item input[type="radio"][checked]');
  if (selectedMessageEl) {
    const titleEl = selectedMessageEl.closest(".quick-messages-list-item")?.querySelector(".quick-messages-list-item-title");
    automaticMessage = cleanText(titleEl);
  }

  const referenceNumber = readInput(["#jobCodeFormInput", 'input[name="Referans Numarası"]', "#jobCode input"]);
  const companyProfile = ms(["#companyProfiles", "#companyProfilesFormGroup", '[name="Şirket Sayfası"]'], ["Şirket Sayfası"]);
  const vueModel = harvestVueJobModel();

  const result = {
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

  if (vueModel) {
    const setS = (key, ...vals) => {
      if (result[key]) return;
      for (const v of vals) {
        const s = asText(v);
        if (s && !isJunk(s) && s !== "[]") { result[key] = s; return; }
      }
    };
    const setL = (key, ...vals) => {
      if (Array.isArray(result[key]) && result[key].length) return;
      for (const v of vals) {
        const lst = asList(v);
        if (lst.length) { result[key] = lst; return; }
      }
    };
    setS("ilan_basligi", vueModel.title, vueModel.jobTitle, vueModel.advertisementTitle, vueModel.ilanBasligi);
    setS("pozisyon", vueModel.position && (vueModel.position.displayName || vueModel.position), vueModel.jobPosition, vueModel.positionName);
    setS("departman", vueModel.businessArea, vueModel.department, vueModel.departman);
    setS("calisma_sekli", vueModel.workingType, vueModel.workingTypeList);
    setS("calisma_tercihi", vueModel.remoteWorkType);
    setS("pozisyon_seviyesi", vueModel.positionLevel, vueModel.positionLevelList);
    setS("referans_no", vueModel.jobCode, vueModel.referenceNumber, vueModel.referanceNumber, vueModel.refNo);
    setS("sirket_sayfasi", vueModel.companyProfile, vueModel.companyName, vueModel.company);
    setL("lokasyon", vueModel.jobLocation, vueModel.locations, vueModel.city);
    setL("candidate_location", vueModel.candidateLocation);
    setL("egitim_seviyesi", vueModel.educationLevel, vueModel.educationLevels);
    setL("bolumler", vueModel.department, vueModel.departments);
    setL("yetenekler", vueModel.keywords, vueModel.skills, vueModel.keyword);
    setL("calistigi_pozisyonlar", vueModel.applicantPosition, vueModel.candidatePositions);
    setL("calistigi_sektorler", vueModel.applicantSector, vueModel.candidateSectors);
    if (!result.secili_sorular.length) {
      const qs = vueModel.questions || vueModel.selectedQuestions || vueModel.jobQuestions || [];
      if (Array.isArray(qs)) {
        result.secili_sorular = qs.filter((q) => q && (q.selected || q.isSelected || q.checked))
          .map((q) => asText(q) || q.question || q.text || "").filter(Boolean);
      }
    }
    if (!result.otomatik_mesaj) {
      const msg = vueModel.quickMessage || vueModel.automaticMessage || vueModel.autoMessage;
      const s = asText(msg);
      if (s) result.otomatik_mesaj = s;
    }
  }

  return result;
}
"""

_OVERLAY_KILLER_JS = r"""
(() => {
    if (window.__overlayKillerInstalled) return;
    window.__overlayKillerInstalled = true;
    const KNOWN_SELECTORS = [
        '.modal-backdrop', '.mfp-bg', '.mfp-wrap',
        '[class*="wis-mfp-content"]', '#wis-lightbox',
        '[class*="wis-offer-counter-reminder"]', '[class*="wis-offer-counter-modal"]',
        '[class*="wis-offer"]'
    ];
    const isSiteChrome = (el) => {
        return el.closest(
            '#main_sidebar_menu, .sidebarnew, #dashboard, .sub-header, ' +
            '#nav_collapse_new, .sidebarmenu-wrapper, .dropdown-menu, .multiselect, .new-jobpage, .job-card, .resume-card'
        ) !== null;
    };
    const looksLikeFullscreenOverlay = (el) => {
        if (isSiteChrome(el)) return false;
        let st;
        try { st = getComputedStyle(el); } catch (e) { return false; }
        if (!st || !['fixed', 'sticky'].includes(st.position)) return false;
        const z = parseInt(st.zIndex, 10);
        if (!z || z < 999) return false;
        const r = el.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight;
        if (r.width < vw * 0.3 || r.height < vh * 0.3) return false;
        return true;
    };
    const kill = (el) => {
        try {
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
            el.style.setProperty('pointer-events', 'none', 'important');
        } catch (e) {}
    };
    const sweep = () => {
        try {
            KNOWN_SELECTORS.forEach((sel) => {
                document.querySelectorAll(sel).forEach((el) => {
                    if (!isSiteChrome(el)) kill(el);
                });
            });
            document.querySelectorAll('body > *, #app > *').forEach((el) => {
                if (looksLikeFullscreenOverlay(el)) kill(el);
            });
        } catch (e) {}
        try {
            document.documentElement.style.setProperty('overflow', 'auto', 'important');
            if (document.body) {
                document.body.style.setProperty('overflow', 'auto', 'important');
                document.body.classList.remove('modal-open');
            }
        } catch (e) {}
    };
    sweep();
    const mo = new MutationObserver(() => sweep());
    const start = () => mo.observe(document.documentElement, { childList: true, subtree: true });
    if (document.documentElement) {
        start();
    } else {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    }
    setInterval(sweep, 1000);
})();
"""

_UNHIDE_WIZARD_JS = r"""
() => {
  const keep = /clipPath|gradient|skeleton/i;
  document.querySelectorAll('.new-jobpage [style*="display: none"], .new-jobpage-content').forEach((el) => {
    const preview = (el.innerHTML || "").slice(0, 240);
    if (keep.test(preview) && el.querySelector("svg") && !el.querySelector(".multiselect, .question-item, #jobCodeFormInput")) {
      return;
    }
    if (el.querySelector(".multiselect, .trumbowyg-editor, .question-item, #jobCodeFormInput, #companyProfiles, #keyword")) {
      el.style.setProperty("display", "block", "important");
      el.style.setProperty("visibility", "visible", "important");
    }
  });
}
"""


def _wizard_js() -> str:
    src = _EXTRACT_WIZARD_JS.strip()
    return f"({src})()" if src.startswith("()") else src


def _is_filled(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, list):
        return any(str(x).strip() for x in val)
    if isinstance(val, str):
        s = val.strip()
        return bool(s) and s != "[]"
    return True


def _has_wizard_signal(data: Dict[str, Any]) -> bool:
    for key in (
        "pozisyon",
        "ilan_basligi",
        "departman",
        "lokasyon",
        "yetenekler",
        "ilan_aciklamasi",
        "calistigi_pozisyonlar",
        "sirket_sayfasi",
    ):
        if _is_filled(data.get(key)):
            return True
    return False


def _merge_filled(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, val in (extra or {}).items():
        if _is_filled(val) or key not in out:
            if _is_filled(val) or not _is_filled(out.get(key)):
                out[key] = val
    return out


def _public_wizard(data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(data or {})
    data.pop("_vue_model_found", None)
    return data


def _job_id_from_text(*values: Any) -> str:
    for raw in values:
        if not raw:
            continue
        text = str(raw)
        for pat in (
            r"jobId=(\d+)",
            r"/ilan/detay/(\d+)",
            r"ilan-(\d+)",
            r"/is-ilani/[^?\s]*?(\d{5,})",
            r"/ozgecmis-detay/(\d+)",
            r"/basvuru-listesi\?[^#]*jobId=(\d+)",
        ):
            m = re.search(pat, text, re.I)
            if m:
                return m.group(1)
        if re.fullmatch(r"\d{5,}", text.strip()):
            return text.strip()
    return ""


def _candidates_url(job_id: str) -> str:
    return f"{ATS_ORIGIN}/basvuru-listesi?jobId={job_id}&page=1&aType=0"


def _wizard_url(job_id: str, job_type: str = "active") -> str:
    return f"{ATS_ORIGIN}/ilan/detay/{job_id}?step=1&jobTypes={job_type or 'active'}"


async def install_overlay_killer(context: Any) -> None:
    try:
        await context.add_init_script(_OVERLAY_KILLER_JS)
        logger.info("Overlay killer installed on browser context.")
    except Exception as e:
        logger.warning("Failed to install overlay killer: %s", e)


async def _wait_for_selector_resilient(page: Page, selector: str, timeout: float = 25.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible(timeout=500):
                return True
        except Exception:
            pass
        await dismiss_overlays(page)
        await clear_blocking_popups(page)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await page.wait_for_timeout(500)
    try:
        loc = page.locator(selector).first
        return await loc.count() > 0 and await loc.is_visible(timeout=500)
    except Exception:
        return False


async def _safe_goto(page: Page, url: str, ready: str = "", timeout: float = 20.0) -> None:
    await dismiss_overlays(page)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
    except Exception as e:
        logger.warning("Navigation issue for %s: %s", url, e)
    await dismiss_overlays(page)
    await clear_blocking_popups(page)
    if ready:
        await _wait_for_selector_resilient(page, ready, timeout=min(timeout, 15.0))


_WIZARD_READY_SELECTOR = (
    "#jobPosition, #jobPositionFormGroup, .multiselect__single, "
    ".multiselect__tag, .trumbowyg-editor, input#titleFormInput, .new-jobpage"
)


async def hydrate_wizard_steps(page: Page) -> None:
    await dismiss_overlays(page)
    await clear_blocking_popups(page)
    ok = await _wait_for_selector_resilient(page, _WIZARD_READY_SELECTOR, timeout=20.0)
    if not ok:
        logger.warning("Wizard fields not visible yet; will still try stepper + extract.")
    try:
        await page.evaluate(_UNHIDE_WIZARD_JS)
    except Exception:
        pass
    try:
        links = page.locator(
            "#toc-stepper-ul a:not(.disabled-stepper), .vertical-stepper a:not(.disabled-stepper)"
        )
        count = await links.count()
        for i in range(count):
            try:
                await links.nth(i).click(force=True, timeout=1500)
                await page.wait_for_timeout(350)
                await dismiss_overlays(page)
                try:
                    await page.evaluate(_UNHIDE_WIZARD_JS)
                except Exception:
                    pass
            except Exception:
                continue
        if count:
            try:
                await links.nth(0).click(force=True, timeout=1500)
                await page.wait_for_timeout(250)
            except Exception:
                pass
    except Exception as e:
        logger.debug("Stepper hydration skipped: %s", e)


async def _live_input(page: Page, selector: str) -> str:
    try:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            return ""
        val = await loc.input_value(timeout=800)
        val = (val or "").strip()
        if val and val != "[]":
            return val
    except Exception:
        pass
    return ""


async def extract_wizard_job_details(page: Page) -> Dict[str, Any]:
    await hydrate_wizard_steps(page)
    data: Dict[str, Any] = {}
    for attempt in range(8):
        try:
            chunk = await page.evaluate(_wizard_js())
        except Exception as e:
            logger.warning("Wizard evaluate failed (attempt %d): %s", attempt + 1, e)
            chunk = {}
        if isinstance(chunk, dict):
            data = _merge_filled(data, chunk)
        if isinstance(data, dict) and _has_wizard_signal(data) and attempt >= 1:
            if not data.get("ilan_basligi"):
                data["ilan_basligi"] = await _live_input(page, "#titleFormInput")
            if not data.get("referans_no"):
                data["referans_no"] = await _live_input(page, "#jobCodeFormInput")
            if _has_wizard_signal(data):
                return _public_wizard(data)
        await dismiss_overlays(page)
        await page.wait_for_timeout(400)
        if attempt in (2, 5):
            await hydrate_wizard_steps(page)
    if not data.get("ilan_basligi"):
        data["ilan_basligi"] = await _live_input(page, "#titleFormInput")
    if not data.get("referans_no"):
        data["referans_no"] = await _live_input(page, "#jobCodeFormInput")
    logger.warning("Wizard extract finished without a strong signal; returning last payload.")
    return _public_wizard(data if isinstance(data, dict) else {})


async def extract_candidate_cv_detail(page: Page) -> Dict[str, Any]:
    return await page.evaluate(
        r"""() => {
            const t = el => (el?.textContent || el?.innerText || '').replace(/\s+/g, ' ').trim();
            return {
                extracted_at: new Date().toISOString(),
                candidate_name: t(document.querySelector('.resume-candidate-card .name')) || "",
                candidate_title: t(document.querySelector('.resume-candidate-card .lg.font-weight-bold')) || "",
                location: t(document.querySelector('#shortAddress')) || "",
                birth_date: t(document.querySelector('#birthDate')) || "",
                gender: t(document.querySelector('#sex')) || "",
                experiences: [...document.querySelectorAll('.work-information .list-content-wrapper')].map(exp => ({
                    title: t(exp.querySelector('.bold.md')),
                    duration: t(exp.querySelector('.xs.col-5')),
                    sector: t(exp.querySelector('.summary-info-item:nth-child(1) .summary-label')),
                })),
                education: [...document.querySelectorAll('.education-information .education-wrapper')].map(edu => ({
                    school: t(edu.querySelector('.name')),
                    degree: t(edu.querySelector('.f-major')),
                    years: t(edu.querySelector('.year')),
                }))
            };
        }"""
    )


async def extract_job_card_metadata(card_locator: Locator) -> Dict[str, Any]:
    try:
        title_el = card_locator.locator("h2.new-job-title a, h2 a, a.xl").first
        title = await title_el.text_content() if await title_el.count() else ""
        href = await title_el.get_attribute("href") if await title_el.count() else ""
        ref_el = card_locator.locator(".top_bar-ref").first
        ref_no = await ref_el.text_content() if await ref_el.count() else ""
        company_el = card_locator.locator(".job-card_profile-name").first
        company = await company_el.text_content() if await company_el.count() else ""
        apps_el = card_locator.locator(
            ".count-item:has(.count-label:has-text('Başvuru')) a span"
        ).first
        if await apps_el.count() == 0:
            apps_el = (
                card_locator.locator(".count-item .count-label:has-text('Başvuru')")
                .locator("..")
                .locator("a span, h2, span.xl, a")
                .first
            )
        apps_count = await apps_el.text_content() if await apps_el.count() else "0"
        info_el = card_locator.locator("i.icon-info[id]").first
        info_id = await info_el.get_attribute("id") if await info_el.count() else ""
        job_id = _job_id_from_text(info_id, href)
        return {
            "title": (title or "").strip(),
            "href": href or "",
            "reference_number": (ref_no or "").strip(),
            "company": (company or "").strip(),
            "applications_count": re.sub(r"\s+", "", (apps_count or "").strip()) or "0",
            "job_id": job_id,
        }
    except Exception as e:
        logger.warning("Error parsing single job card: %s", e)
        return {}


async def clear_blocking_popups(page: Page) -> None:
    click_targets = [
        ".wis-offer-counter-reminder-0000-content",
        "div[class*='wis-offer-counter-reminder']",
        "[class*='wis-mfp-close']",
        "button.mfp-close",
        "#wis-lightbox button",
        ".mfp-wrap button.close",
        ".modal.show [aria-label='Close']",
        ".modal.show .btn-close",
        ".popup-close-btn",
    ]
    for selector in click_targets:
        try:
            target = page.locator(selector).first
            if await target.is_visible(timeout=400):
                logger.info("Triggered auto-click on target: %s", selector)
                await target.click(force=True)
                await page.wait_for_timeout(200)
        except Exception:
            pass


async def dismiss_overlays(page: Page) -> None:
    try:
        await page.add_style_tag(
            content="""
            .modal-backdrop, .mfp-bg, .mfp-wrap,
            [class*="wis-mfp-content"], #wis-lightbox,
            div[class*="wis-offer-counter-reminder"],
            div[class*="wis-offer-counter-modal"],
            div[class*="wis-offer"] {
                display: none !important;
                visibility: hidden !important;
                pointer-events: none !important;
            }
            body, html { overflow: auto !important; }
        """
        )
    except Exception as e:
        logger.debug("Overlay CSS injection skipped: %s", e)


async def is_user_logged_in(page: Page) -> bool:
    logged_in_selectors = [
        "#user-info",
        "#dashboard-job-list",
        "#dashboard-articles-list",
        "#job-list-page",
        ".page-view",
    ]
    for selector in logged_in_selectors:
        try:
            if await page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


async def _extract_candidates_from(
    target: Page,
    max_candidates: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if max_candidates is None:
        max_candidates = limit

    all_candidates: List[Dict[str, Any]] = []
    seen_keys = set()

    candidate_container_selectors = [
        ".resume-card",
        "a[href*='/ozgecmis-detay/']",
        ".candidate-card",
        ".applicant-card",
        ".resume-card_wrapper",
        ".applicant-list-page-container",
        ".candidate-list-wrapper",
        "table.applicant-table",
    ]

    loaded = False
    for sel in candidate_container_selectors:
        try:
            if await target.locator(sel).first.is_visible(timeout=2000):
                loaded = True
                break
        except Exception:
            pass

    if not loaded:
        logger.info("Candidate elements not immediately visible; performing resilient wait...")
        for sel in candidate_container_selectors:
            if await _wait_for_selector_resilient(target, sel, timeout=4.0):
                loaded = True
                break

    if not loaded:
        logger.warning(
            "Target page candidate containers did not signal readiness; executing fallbacks directly."
        )

    await dismiss_overlays(target)
    await clear_blocking_popups(target)

    empty_pages = 0
    while True:
        remaining_limit = (
            (max_candidates - len(all_candidates)) if max_candidates is not None else None
        )

        page_candidates: List[Dict[str, Any]] = []
        try:
            raw = await target.evaluate(_EXTRACT_CANDIDATES_MULTI_FALLBACK_JS, remaining_limit)
            if isinstance(raw, list):
                page_candidates = raw
        except Exception as e:
            logger.warning("Candidate list extract failed on current page: %s", e)

        added = 0
        for cand in page_candidates:
            if not isinstance(cand, dict):
                continue
            name = (cand.get("name") or "").strip()
            title = (cand.get("title") or "").strip()
            detail_url = (cand.get("detail_url") or "").replace("&", "&").strip()
            key = (detail_url.split("?")[0] or name).lower()
            if not name and not detail_url:
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_candidates.append({"name": name, "title": title, "detail_url": detail_url})
            added += 1

        if not added:
            empty_pages += 1
            logger.warning("No new candidate records harvested on current pagination view.")
        else:
            empty_pages = 0

        if max_candidates is not None and len(all_candidates) >= max_candidates:
            all_candidates = all_candidates[:max_candidates]
            logger.info(
                "Reached candidate limit (%d candidates). Stopping pagination.", max_candidates
            )
            break

        if empty_pages >= 2:
            break

        next_btn = target.locator(
            "ul.pagination li.page-item:has-text('Sonraki'), "
            "li.page-item:has(a.page-link:has-text('Sonraki'))"
        ).first
        if await next_btn.count() == 0:
            break

        class_attr = await next_btn.get_attribute("class") or ""
        if "disabled" in class_attr:
            logger.info(
                "Reached final candidate page (%d candidates extracted).", len(all_candidates)
            )
            break

        next_link = next_btn.locator("a.page-link, a").first
        if await next_link.count() == 0:
            break
        try:
            await next_link.click(force=True, timeout=4000)
            try:
                await target.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass
            await target.wait_for_timeout(1200)
            await dismiss_overlays(target)
        except Exception:
            break

    return all_candidates


def _backfill_from_card(record: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_filled(record.get("ilan_basligi")):
        record["ilan_basligi"] = record.get("title") or ""
    if not _is_filled(record.get("referans_no")):
        record["referans_no"] = record.get("reference_number") or ""
    if not _is_filled(record.get("sirket_sayfasi")):
        record["sirket_sayfasi"] = record.get("company") or ""
    return record


async def _collect_listing_jobs(page: Page, route: str, limit: int) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    base_tab_url = f"{ATS_ORIGIN}{route}"
    logger.info("Navigating to category tab: %s", route)
    await _safe_goto(page, base_tab_url, ".wide-card.job-card, .job-card", timeout=20.0)

    card_selector = ".wide-card.job-card, .job-card.wide-card"
    while len(jobs) < limit:
        if not await _wait_for_selector_resilient(page, card_selector, timeout=15.0):
            logger.warning("No job cards found for category %s. Moving on.", route)
            break

        count = await page.locator(card_selector).count()
        logger.info("Found %d job cards on tab %s.", count, route)
        for i in range(count):
            if len(jobs) >= limit:
                break
            card = page.locator(card_selector).nth(i)
            meta = await extract_job_card_metadata(card)
            if not meta.get("title") and not meta.get("job_id"):
                continue
            meta["category_tab"] = route.rstrip("/").split("/")[-1]
            jobs.append(meta)

        if len(jobs) >= limit:
            break

        next_btn_container = page.locator("li.page-item", has_text="Sonraki").first
        if await next_btn_container.count() == 0:
            break
        class_attr = await next_btn_container.get_attribute("class") or ""
        if "disabled" in class_attr:
            logger.info("Reached end of pagination for %s.", route)
            break
        next_link = next_btn_container.locator("a.page-link").first
        if await next_link.count() == 0:
            break
        try:
            await next_link.click(force=True, timeout=4000)
            await page.wait_for_timeout(1800)
            await dismiss_overlays(page)
        except Exception:
            break

    return jobs


async def _extract_candidates_for_job(
    page: Page,
    job_id: str,
    filters: Dict[str, Any],
    max_candidates_per_job: Optional[int],
    listing_url: str = "",
    card_index: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if max_candidates_per_job == 0:
        return []

    opened = False
    if job_id:
        await _safe_goto(
            page,
            _candidates_url(job_id),
            ".resume-card, a[href*='/ozgecmis-detay/'], .resume-card_wrapper",
            timeout=20.0,
        )
        opened = (
            "/basvuru-listesi" in (page.url or "") or await page.locator(".resume-card").count() > 0
        )

    if not opened and listing_url and card_index is not None:
        try:
            await _safe_goto(page, listing_url, ".wide-card.job-card, .job-card", timeout=15.0)
            card = page.locator(".wide-card.job-card, .job-card.wide-card").nth(card_index)
            toggle = card.locator(".dropdown-toggle-split, button[data-toggle='dropdown']").first
            if await toggle.count():
                await toggle.click(force=True, timeout=2000)
                await page.wait_for_timeout(350)
            see_apps = page.locator("button[name='displayApplications']").first
            await see_apps.click(force=True, timeout=2500)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(800)
            opened = True
        except Exception as e:
            logger.warning("UI fallback for applications failed: %s", e)

    if not opened:
        return []

    await apply_ats_form_filters(page, filters)
    return await _extract_candidates_from(page, max_candidates=max_candidates_per_job)


async def _extract_wizard_for_job(
    page: Page,
    job_id: str,
    job_type: str,
    listing_url: str = "",
    card_index: Optional[int] = None,
) -> Dict[str, Any]:
    opened = False
    if job_id:
        await _safe_goto(page, _wizard_url(job_id, job_type), _WIZARD_READY_SELECTOR, timeout=20.0)
        opened = (
            "/ilan/detay/" in (page.url or "")
            or await page.locator(".new-jobpage").count() > 0
            or await page.locator("#jobPositionFormGroup").count() > 0
        )

    if not opened and listing_url and card_index is not None:
        try:
            await _safe_goto(page, listing_url, ".wide-card.job-card, .job-card", timeout=15.0)
            card = page.locator(".wide-card.job-card, .job-card.wide-card").nth(card_index)
            edit_btn = card.locator("button[name='editAdd']").first
            await edit_btn.click(force=True, timeout=2500)
            await page.wait_for_load_state("domcontentloaded")
            opened = True
        except Exception as e:
            logger.warning("UI fallback for wizard failed: %s", e)

    if not opened:
        return {}
    return await extract_wizard_job_details(page)


async def process_jobs_task(
    page: Page,
    limit: int = 100,
    max_candidates_per_job: Optional[int] = None,
    filters: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    logger.info(
        "Starting Multi-Step Pipeline process_jobs_task (limit=%d, max_candidates_per_job=%s)...",
        limit,
        str(max_candidates_per_job),
    )
    filters = filters or {}

    try:
        await dismiss_overlays(page)
        await clear_blocking_popups(page)

        if await is_user_logged_in(page):
            logger.info("User dashboard detected. Post-login state confirmed.")

        current_url = page.url or ""
        job_id_on_page = _job_id_from_text(current_url)

        if await page.locator("#resume-left-tabs").count() > 0:
            logger.info("Detected CV detail page. Extracting CV details...")
            details = await extract_candidate_cv_detail(page)
            return [details]

        on_wizard = (
            await page.locator(".new-jobpage").count() > 0
            or await page.locator("#jobPositionFormGroup").count() > 0
            or "/ilan/detay/" in current_url
        )
        on_candidates = (
            "/basvuru-listesi" in current_url
            or await page.locator("a[href*='/ozgecmis-detay/']").count() > 0
        ) and await page.locator(".wide-card.job-card").count() == 0

        if on_wizard or (on_candidates and job_id_on_page):
            logger.info("Detected single-job page. Building full job record...")
            record: Dict[str, Any] = {
                "title": "",
                "href": current_url,
                "reference_number": "",
                "company": "",
                "applications_count": "0",
                "candidates": [],
                "job_id": job_id_on_page,
            }
            if on_candidates and job_id_on_page:
                await apply_ats_form_filters(page, filters)
                record["candidates"] = await _extract_candidates_from(
                    page, max_candidates=max_candidates_per_job
                )
                wizard_data = await _extract_wizard_for_job(page, job_id_on_page, "active")
                record = _merge_filled(record, wizard_data)
            else:
                wizard_data = await extract_wizard_job_details(page)
                record = _merge_filled(record, wizard_data)
                if job_id_on_page:
                    record["candidates"] = await _extract_candidates_for_job(
                        page, job_id_on_page, filters, max_candidates_per_job
                    )
            if not record.get("title"):
                record["title"] = record.get("ilan_basligi") or record.get("pozisyon") or ""
            if not record.get("reference_number"):
                record["reference_number"] = record.get("referans_no") or ""
            if not record.get("company"):
                record["company"] = record.get("sirket_sayfasi") or ""
            return [_backfill_from_card(record)]

        target_routes = [
            route for toggle, route in TAB_ROUTES.items() if filters.get(toggle, False)
        ]
        if not target_routes:
            target_routes = [TAB_ROUTES["include_active"]]

        jobs_processed: List[Dict[str, Any]] = []

        for route in target_routes:
            remaining = limit - len(jobs_processed)
            if remaining <= 0:
                break

            listing = await _collect_listing_jobs(page, route, remaining)
            job_type = JOB_TYPE_BY_ROUTE.get(route, "active")
            listing_url = f"{ATS_ORIGIN}{route}"

            for idx, job_record in enumerate(listing):
                if len(jobs_processed) >= limit:
                    break
                job_id = job_record.get("job_id") or _job_id_from_text(
                    job_record.get("href"), job_record.get("title")
                )
                logger.info(
                    "Processing job %d/%d (%s / %s)...",
                    idx + 1,
                    len(listing),
                    job_record.get("title") or "?",
                    job_id or "no-id",
                )
                job_record["candidates"] = []

                try:
                    job_record["candidates"] = await _extract_candidates_for_job(
                        page,
                        job_id,
                        filters,
                        max_candidates_per_job,
                        listing_url=listing_url,
                        card_index=idx,
                    )
                except Exception as e:
                    logger.warning("Candidate extraction failed for job %s: %s", job_id, e)

                try:
                    wizard_data = await _extract_wizard_for_job(
                        page,
                        job_id,
                        job_type,
                        listing_url=listing_url,
                        card_index=idx,
                    )
                    job_record = _merge_filled(job_record, wizard_data)
                except Exception as e:
                    logger.warning("Wizard extraction failed for job %s: %s", job_id, e)

                jobs_processed.append(_backfill_from_card(job_record))

        logger.info(
            "Job processing finished. Total extracted across categories: %d", len(jobs_processed)
        )
        return jobs_processed

    except Exception as err:
        logger.exception("Error during job processing: %s", err)
        raise err


ACCORDION_PANELS = {
    "personal": ("personalInfo", "KİŞİSEL BİLGİLER"),
    "education": ("educationInfo", "EĞİTİM"),
    "experience": ("experienceInfo", "İŞ DENEYİMİ"),
    "location": ("locationInfo", "LOKASYON"),
    "application": ("applicationInfo", "BAŞVURU SÜRECİ"),
    "kvkk": ("kvkk", "KVKK ONAY DURUMU"),
    "review_status": ("moreInfo", "İŞLEMLER"),
}

SCOPE_MAP = {
    "all_jobs": "0",
    "last_job": "1",
    "last_3_jobs": "2",
}

_CANDIDATE_FILTER_KEYS = (
    "personal",
    "education",
    "experience",
    "location",
    "application",
    "kvkk",
    "review_status",
)


async def apply_ats_form_filters(page: Page, filters: Dict[str, Any]):
    if not filters:
        return
    if not any(filters.get(k) for k in _CANDIDATE_FILTER_KEYS):
        return

    try:

        async def _ensure_panel_open(panel_id: str, header_title: str):
            try:
                panel = page.locator(f"#{panel_id}").first
                if not await panel.is_visible(timeout=1000):
                    logger.info("Opening filter panel: %s (#%s)", header_title, panel_id)

                    header = (
                        page.locator(f"#{panel_id}")
                        .locator(
                            "xpath=preceding-sibling::div[contains(@class, 'filter-collapse')]"
                        )
                        .first
                    )

                    if not await header.is_visible(timeout=1000):
                        header = page.locator("div.filter-collapse", has_text=header_title).first

                    if await header.is_visible(timeout=1000):
                        await header.click(force=True)
                        await panel.wait_for(state="visible", timeout=3000)
            except Exception as e:
                logger.warning(f"Could not open accordion panel {panel_id}: {e}")

        async def _fill_vue_multiselect(
            container_selector: str, input_selector: str, items: List[str]
        ):
            if not items:
                return
            for item in items:
                try:
                    container = page.locator(container_selector).first
                    if not await container.is_visible(timeout=1000):
                        continue

                    inp = container.locator(input_selector).first
                    await inp.click(force=True)
                    await inp.fill(str(item))
                    await page.wait_for_timeout(400)

                    opt = container.locator(".multiselect__option", has_text=str(item)).first
                    if await opt.is_visible(timeout=1500):
                        await opt.click(force=True)
                    else:
                        await page.keyboard.press("Enter")
                    await page.wait_for_timeout(200)
                except Exception as e:
                    logger.warning(
                        f"Failed to fill multiselect '{container_selector}' with '{item}': {e}"
                    )

        personal = filters.get("personal")
        if personal:
            await _ensure_panel_open(*ACCORDION_PANELS["personal"])

            if personal.get("first_name"):
                try:
                    name_input = page.locator("#name").first
                    if await name_input.is_visible(timeout=1000):
                        await name_input.fill(personal["first_name"])
                except Exception:
                    pass

            if personal.get("last_name"):
                try:
                    surname_input = page.locator("#surname").first
                    if await surname_input.is_visible(timeout=1000):
                        await surname_input.fill(personal["last_name"])
                except Exception:
                    pass

            gender = personal.get("gender") or {}
            if gender.get("male"):
                try:
                    chk = page.locator("input[name='man']").first
                    if await chk.is_visible(timeout=1000) and not await chk.is_checked():
                        await chk.check(force=True)
                except Exception:
                    pass

            if gender.get("female"):
                try:
                    chk = page.locator("input[name='woman']").first
                    if await chk.is_visible(timeout=1000) and not await chk.is_checked():
                        await chk.check(force=True)
                except Exception:
                    pass

            await _fill_vue_multiselect(
                "div.multiselect[name='nationality']",
                "input.multiselect__input",
                personal.get("nationality", []),
            )
            await _fill_vue_multiselect(
                "div.multiselect[name='militaryStatus']",
                "input.multiselect__input",
                personal.get("military_status", []),
            )
            await _fill_vue_multiselect(
                "div.multiselect[name='driverLicence']",
                "input.multiselect__input",
                personal.get("driver_licences", []),
            )

            langs = personal.get("languages", [])
            if langs:
                lang_names = [
                    l["language"] for l in langs if isinstance(l, dict) and l.get("language")
                ]
                await _fill_vue_multiselect(
                    "div.multiselect[name='language']", "input.multiselect__input", lang_names
                )

                first_level = next(
                    (
                        l.get("min_level")
                        for l in langs
                        if isinstance(l, dict) and l.get("min_level")
                    ),
                    None,
                )
                if first_level:
                    await _fill_vue_multiselect(
                        "div.multiselect[name='languageLevel']",
                        "input.multiselect__input",
                        [first_level],
                    )

            if personal.get("is_disabled_candidate"):
                try:
                    disabled_sw = page.locator(".equality-filter input[type='checkbox']").first
                    if (
                        await disabled_sw.is_visible(timeout=1000)
                        and not await disabled_sw.is_checked()
                    ):
                        await disabled_sw.check(force=True)
                except Exception:
                    pass

            if personal.get("is_disaster_affected"):
                try:
                    disaster_sw = page.locator(".ug-filter-disaster input[type='checkbox']").first
                    if (
                        await disaster_sw.is_visible(timeout=1000)
                        and not await disaster_sw.is_checked()
                    ):
                        await disaster_sw.check(force=True)
                except Exception:
                    pass

        education = filters.get("education")
        if education:
            await _ensure_panel_open(*ACCORDION_PANELS["education"])
            await _fill_vue_multiselect(
                "#educationLevel", "#educationLevelFormInput", education.get("levels", [])
            )
            await _fill_vue_multiselect(
                "div.multiselect[name='university']",
                "input.multiselect__input",
                education.get("universities", []),
            )
            await _fill_vue_multiselect(
                "#department", "#departmentFormInput", education.get("departments", [])
            )

        exp = filters.get("experience")
        if exp:
            await _ensure_panel_open(*ACCORDION_PANELS["experience"])

            exp_type = exp.get("experience_type")
            if exp_type in ["inexperienced", "experienced"]:
                try:
                    val_idx = "1" if exp_type == "inexperienced" else "2"
                    radio = page.locator(f"input[name='radiosStacked'][value='{val_idx}']").first
                    if await radio.is_visible(timeout=1000):
                        await radio.check(force=True)
                except Exception:
                    pass

            if exp.get("positions"):
                try:
                    p_scope = exp.get("position_scope", "all_jobs")
                    p_select = page.locator("#position").locator("..").locator("select.xs").first
                    if await p_select.is_visible(timeout=1000):
                        await p_select.select_option(value=SCOPE_MAP.get(p_scope, "0"))
                except Exception:
                    pass
                await _fill_vue_multiselect("#position", "#positionFormInput", exp["positions"])

            if exp.get("sectors"):
                try:
                    s_scope = exp.get("sector_scope", "all_jobs")
                    s_select = page.locator("#sector").locator("..").locator("select.xs").first
                    if await s_select.is_visible(timeout=1000):
                        await s_select.select_option(value=SCOPE_MAP.get(s_scope, "0"))
                except Exception:
                    pass
                await _fill_vue_multiselect("#sector", "#sectorFormInput", exp["sectors"])

            if exp.get("is_currently_working") is True:
                try:
                    chk = page.locator("input[name='working']").first
                    if await chk.is_visible(timeout=1000):
                        await chk.check(force=True)
                except Exception:
                    pass
            elif exp.get("is_currently_working") is False:
                try:
                    chk = page.locator("input[name='does-not-work']").first
                    if await chk.is_visible(timeout=1000):
                        await chk.check(force=True)
                except Exception:
                    pass

        location = filters.get("location")
        if location:
            await _ensure_panel_open(*ACCORDION_PANELS["location"])
            await _fill_vue_multiselect(
                "#location", "#locationFormInput", location.get("current_locations", [])
            )
            await _fill_vue_multiselect(
                "div.multiselect[name='preferCity']",
                "input.multiselect__input",
                location.get("preferred_cities", []),
            )

        try:
            submit_btn = page.locator("div.filter-footer button[type='submit']").first
            if await submit_btn.is_visible(timeout=2000):
                logger.info("Submitting filter criteria via 'Ara' button...")
                await submit_btn.click(force=True)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    await page.wait_for_timeout(1500)
                await page.wait_for_timeout(800)
        except Exception as e:
            logger.warning(f"Error submitting the filter form: {e}")

    except Exception as err:
        logger.warning(
            f"Unexpected error encountered while populating candidate form filters: {err}"
        )


async def extract_and_send_jobs(
    page: Page, target_api_url: str, limit: int = 100
) -> Dict[str, Any]:
    logger.info("Starting job extraction task...")
    extracted_jobs = await process_jobs_task(page, limit=limit)
    payload = {
        "status": "success",
        "total_jobs": len(extracted_jobs),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "jobs": extracted_jobs,
    }
    logger.info("Sending extracted payload to %s...", target_api_url)
    async with aiohttp.ClientSession() as http_session:
        try:
            async with http_session.post(target_api_url, json=payload, timeout=30) as resp:
                status_code = resp.status
                response_text = await resp.text()
                logger.info("POST request returned status: %d", status_code)
                return {
                    "http_status": status_code,
                    "response": response_text,
                    "payload": payload,
                }
        except Exception as e:
            logger.exception("Failed to send POST request: %s", e)
            return {"error": str(e), "payload": payload}


async def extract_current_job(page: Page) -> Dict[str, Any]:
    return await extract_wizard_job_details(page)
