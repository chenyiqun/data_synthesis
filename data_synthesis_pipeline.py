import argparse
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

from gpt_api_client import GPTApiClient
from search_api_client import RunwaySearchClient, SearchResponse


DEFAULT_SEARCH_ENGINES = ["google", "bing", "baidu"]


@dataclass
class SynthesisConfig:
    target_hops: int = 2
    max_candidates_per_hop: int = 5
    max_retry_per_hop: int = 3
    search_engines: List[str] = field(default_factory=lambda: list(DEFAULT_SEARCH_ENGINES))
    search_results_per_engine: int = 5
    min_hop_confidence: float = 0.75
    min_final_confidence: float = 0.75
    enable_fuzzification: bool = True


@dataclass
class Evidence:
    engine: str
    title: str = ""
    link: str = ""
    content: str = ""
    media: str = ""
    publish_date: str = ""
    refer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HopCandidate:
    hop_id: int
    current_target: str
    new_focus: str
    question_to_current: str
    expected_answer: str
    search_query: str
    why_useful: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, hop_id: int, current_target: str, raw: Mapping[str, Any]) -> "HopCandidate":
        return cls(
            hop_id=hop_id,
            current_target=current_target,
            new_focus=str(raw.get("new_focus") or ""),
            question_to_current=str(raw.get("question_to_current") or ""),
            expected_answer=str(raw.get("expected_answer") or current_target),
            search_query=str(raw.get("search_query") or ""),
            why_useful=str(raw.get("why_useful") or ""),
            raw=dict(raw),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerifiedHop:
    hop_id: int
    current_target: str
    new_focus: str
    question_to_current: str
    expected_answer: str
    search_query: str
    verified: bool
    confidence: float
    reason: str
    problems: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    validation_raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass
class FinalValidation:
    is_valid: bool
    is_answer_supported: bool
    is_unique: bool
    confidence: float
    reason: str
    problems: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass
class SyntheticSample:
    answer: str
    query: str
    hop_count: int
    answer_profile: Dict[str, Any]
    reasoning_chain: List[VerifiedHop]
    validation: FinalValidation
    created_at: int
    success: bool
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "query": self.query,
            "hop_count": self.hop_count,
            "answer_profile": self.answer_profile,
            "reasoning_chain": [item.to_dict() for item in self.reasoning_chain],
            "validation": self.validation.to_dict(),
            "created_at": self.created_at,
            "success": self.success,
            "error": self.error,
        }


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    candidates = []
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"Cannot parse JSON from GPT output: {text[:1000]}")


def compact_evidence(search_response: SearchResponse, limit: int) -> List[Evidence]:
    evidence = []
    for item in search_response.results[:limit]:
        evidence.append(
            Evidence(
                engine=search_response.alias,
                title=item.title,
                link=item.link,
                content=item.content,
                media=item.media,
                publish_date=item.publish_date,
                refer=item.refer,
            )
        )
    return evidence


def evidence_for_prompt(evidence: Iterable[Evidence], limit: int = 12) -> List[Dict[str, str]]:
    rows = []
    for index, item in enumerate(list(evidence)[:limit]):
        rows.append(
            {
                "index": str(index),
                "engine": item.engine,
                "title": item.title,
                "link": item.link,
                "content": item.content[:500],
                "media": item.media,
                "publish_date": item.publish_date,
            }
        )
    return rows


class DataSynthesizer:
    def __init__(
        self,
        *,
        gpt_client: Optional[GPTApiClient] = None,
        search_client: Optional[RunwaySearchClient] = None,
        config: Optional[SynthesisConfig] = None,
    ) -> None:
        self.gpt_client = gpt_client or GPTApiClient()
        self.search_client = search_client or RunwaySearchClient()
        self.config = config or SynthesisConfig()

    def close(self) -> None:
        self.gpt_client.close()
        self.search_client.close()

    def __enter__(self) -> "DataSynthesizer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def synthesize(self, answer: str) -> SyntheticSample:
        created_at = int(time.time())
        answer_profile: Dict[str, Any] = {}
        chain: List[VerifiedHop] = []

        try:
            answer_profile = self.profile_answer(answer)
            current_target = answer

            for hop_id in range(1, self.config.target_hops + 1):
                verified_hop = self.build_one_hop(
                    answer=answer,
                    current_target=current_target,
                    chain=chain,
                    hop_id=hop_id,
                    answer_profile=answer_profile,
                )
                chain.append(verified_hop)
                current_target = verified_hop.new_focus

            query = self.generate_final_query(answer, chain, answer_profile)
            validation = self.validate_final_query(answer, query, chain)
            if answer and answer in query:
                validation.is_valid = False
                validation.is_answer_supported = False
                validation.problems.append("query directly contains the final answer")

            success = (
                validation.is_valid
                and validation.is_answer_supported
                and validation.is_unique
                and validation.confidence >= self.config.min_final_confidence
            )

            return SyntheticSample(
                answer=answer,
                query=query,
                hop_count=len(chain),
                answer_profile=answer_profile,
                reasoning_chain=chain,
                validation=validation,
                created_at=created_at,
                success=success,
            )
        except Exception as exc:
            return SyntheticSample(
                answer=answer,
                query="",
                hop_count=len(chain),
                answer_profile=answer_profile,
                reasoning_chain=chain,
                validation=FinalValidation(
                    is_valid=False,
                    is_answer_supported=False,
                    is_unique=False,
                    confidence=0.0,
                    reason="generation failed",
                    problems=[repr(exc)],
                ),
                created_at=created_at,
                success=False,
                error=repr(exc),
            )

    def profile_answer(self, answer: str) -> Dict[str, Any]:
        prompt = f"""
你是数据合成系统的答案画像模块。请分析给定答案的类型，并生成后续搜索验证会用到的信息。

答案：{answer}

只输出 JSON，不要输出解释。格式：
{{
  "answer": "...",
  "answer_type": "person/place/work/company/event/concept/time/number/other",
  "domain": "...",
  "possible_aliases": ["..."],
  "basic_search_queries": ["..."],
  "notes": "..."
}}
"""
        response = self.gpt_client.chat(prompt=prompt)
        response.raise_for_error()
        data = extract_json(response.content)
        if not isinstance(data, dict):
            raise ValueError("answer profile is not a JSON object")
        return data

    def build_one_hop(
        self,
        *,
        answer: str,
        current_target: str,
        chain: List[VerifiedHop],
        hop_id: int,
        answer_profile: Dict[str, Any],
    ) -> VerifiedHop:
        last_error = ""
        rejected: List[Dict[str, Any]] = []

        for retry_index in range(1, self.config.max_retry_per_hop + 1):
            candidates = self.generate_hop_candidates(
                answer=answer,
                current_target=current_target,
                chain=chain,
                hop_id=hop_id,
                answer_profile=answer_profile,
                rejected=rejected,
            )

            for candidate in candidates[: self.config.max_candidates_per_hop]:
                if not candidate.new_focus or not candidate.question_to_current:
                    continue
                if candidate.new_focus == current_target or candidate.new_focus == answer:
                    rejected.append(
                        {
                            "candidate": candidate.to_dict(),
                            "reason": "new_focus duplicates current target or final answer",
                            "problems": ["new_focus is not a useful reverse-hop replacement"],
                            "confidence": 0.0,
                        }
                    )
                    continue

                evidence = self.collect_search_evidence(candidate.search_query or candidate.question_to_current)
                verified_hop = self.validate_hop(candidate, evidence)
                if (
                    verified_hop.verified
                    and verified_hop.confidence >= self.config.min_hop_confidence
                ):
                    return verified_hop

                rejected.append(
                    {
                        "candidate": candidate.to_dict(),
                        "reason": verified_hop.reason,
                        "problems": verified_hop.problems,
                        "confidence": verified_hop.confidence,
                    }
                )
                last_error = verified_hop.reason

            last_error = last_error or f"retry {retry_index} produced no valid candidate"

        raise RuntimeError(f"cannot build hop {hop_id}: {last_error}")

    def generate_hop_candidates(
        self,
        *,
        answer: str,
        current_target: str,
        chain: List[VerifiedHop],
        hop_id: int,
        answer_profile: Dict[str, Any],
        rejected: List[Dict[str, Any]],
    ) -> List[HopCandidate]:
        chain_data = [
            {
                "hop_id": item.hop_id,
                "current_target": item.current_target,
                "new_focus": item.new_focus,
                "question_to_current": item.question_to_current,
                "expected_answer": item.expected_answer,
            }
            for item in chain
        ]
        prompt = f"""
你是复杂 query 逆向合成器。现在要从最终答案反向增加一跳可验证的推理。

最终答案：{answer}
答案画像：{json.dumps(answer_profile, ensure_ascii=False)}
当前需要被替换/解释的目标：{current_target}
已有反向推理链：{json.dumps(chain_data, ensure_ascii=False)}
被拒绝过的候选：{json.dumps(rejected[-8:], ensure_ascii=False)}

请生成 {self.config.max_candidates_per_hop} 个候选跳。每个候选跳应该满足：
1. question_to_current 这个问题的答案应该是 current_target。
2. new_focus 是一个新的实体、事件、作品、奖项、地点、机构或明确描述，后续还能继续被替换。
3. new_focus 不要等于 current_target，也不要直接等于最终答案。
4. search_query 用于搜索验证这个候选跳，可以包含 current_target 来提高验证准确性。
5. 优先选择事实清楚、搜索结果容易证明、答案唯一的关系。

只输出 JSON，不要输出解释。格式：
{{
  "candidates": [
    {{
      "new_focus": "...",
      "question_to_current": "...",
      "expected_answer": "{current_target}",
      "search_query": "...",
      "why_useful": "..."
    }}
  ]
}}
"""
        response = self.gpt_client.chat(prompt=prompt)
        response.raise_for_error()
        data = extract_json(response.content)
        raw_candidates = data.get("candidates") if isinstance(data, dict) else data
        if not isinstance(raw_candidates, list):
            raise ValueError("hop candidates response does not contain a candidates list")

        candidates = []
        for raw in raw_candidates:
            if isinstance(raw, Mapping):
                candidates.append(HopCandidate.from_raw(hop_id, current_target, raw))
        return candidates

    def collect_search_evidence(self, search_query: str) -> List[Evidence]:
        evidence: List[Evidence] = []
        for engine in self.config.search_engines:
            try:
                response = self.search_client.search(search_query, engine)
                evidence.extend(
                    compact_evidence(response, limit=self.config.search_results_per_engine)
                )
            except Exception as exc:
                evidence.append(
                    Evidence(
                        engine=engine,
                        title="SEARCH_ERROR",
                        content=repr(exc),
                    )
                )
        return evidence

    def validate_hop(self, candidate: HopCandidate, evidence: List[Evidence]) -> VerifiedHop:
        prompt = f"""
你是事实验证器。请根据搜索证据判断候选跳是否成立。

候选跳：
{json.dumps(candidate.to_dict(), ensure_ascii=False)}

搜索证据：
{json.dumps(evidence_for_prompt(evidence), ensure_ascii=False)}

判断标准：
1. question_to_current 的答案是否确实是 expected_answer/current_target。
2. 搜索证据是否支持这个事实。
3. 答案是否基本唯一，没有明显歧义。
4. new_focus 是否适合作为下一轮继续逆向扩展的目标。
5. selected_evidence_indices 使用搜索证据中的 0-based index。

只输出 JSON，不要输出解释。格式：
{{
  "verified": true,
  "is_supported": true,
  "is_unique": true,
  "confidence": 0.0,
  "reason": "...",
  "problems": ["..."],
  "selected_evidence_indices": [0, 1]
}}
"""
        response = self.gpt_client.chat(prompt=prompt)
        response.raise_for_error()
        data = extract_json(response.content)
        if not isinstance(data, dict):
            raise ValueError("hop validation response is not a JSON object")

        selected_indices = data.get("selected_evidence_indices") or []
        selected_evidence = []
        if isinstance(selected_indices, list):
            for index in selected_indices:
                if isinstance(index, int) and 0 <= index < len(evidence):
                    selected_evidence.append(evidence[index])

        if not selected_evidence:
            selected_evidence = evidence[: min(3, len(evidence))]

        confidence = self._safe_float(data.get("confidence"), default=0.0)
        verified = bool(data.get("verified")) and bool(data.get("is_supported")) and bool(data.get("is_unique"))
        problems = data.get("problems") if isinstance(data.get("problems"), list) else []

        return VerifiedHop(
            hop_id=candidate.hop_id,
            current_target=candidate.current_target,
            new_focus=candidate.new_focus,
            question_to_current=candidate.question_to_current,
            expected_answer=candidate.expected_answer,
            search_query=candidate.search_query,
            verified=verified,
            confidence=confidence,
            reason=str(data.get("reason") or ""),
            problems=[str(item) for item in problems],
            evidence=selected_evidence,
            validation_raw=data,
        )

    def generate_final_query(
        self,
        answer: str,
        chain: List[VerifiedHop],
        answer_profile: Dict[str, Any],
    ) -> str:
        chain_data = [item.to_dict() for item in chain]
        prompt = f"""
你是复杂 query 写作器。请根据反向推理链生成一个自然、复杂、可回答的问题。

最终答案：{answer}
答案画像：{json.dumps(answer_profile, ensure_ascii=False)}
反向推理链：{json.dumps(chain_data, ensure_ascii=False)}
是否需要模糊化：{self.config.enable_fuzzification}

要求：
1. 最终问题的答案必须是最终答案。
2. 问题中不要直接出现最终答案。
3. 尽量把链条自然融合成一个问题，而不是列步骤。
4. 如果启用模糊化，可以用描述替代中间实体，但不能模糊到不可验证。
5. 保持答案唯一，不要制造多解。

只输出 JSON，不要输出解释。格式：
{{
  "query": "...",
  "answer": "{answer}",
  "used_hops": [1, 2],
  "rewrite_notes": "..."
}}
"""
        response = self.gpt_client.chat(prompt=prompt)
        response.raise_for_error()
        data = extract_json(response.content)
        if not isinstance(data, dict) or not data.get("query"):
            raise ValueError("final query generation did not return query")
        return str(data["query"]).strip()

    def validate_final_query(
        self,
        answer: str,
        query: str,
        chain: List[VerifiedHop],
    ) -> FinalValidation:
        evidence = self.collect_search_evidence(query)
        prompt = f"""
你是最终样本质检器。请判断复杂 query 是否能被搜索证据和推理链支持，并且答案是否唯一。

query：{query}
预期答案：{answer}
推理链：{json.dumps([item.to_dict() for item in chain], ensure_ascii=False)}
搜索证据：{json.dumps(evidence_for_prompt(evidence), ensure_ascii=False)}

判断标准：
1. query 是否语义清楚、可回答。
2. 根据证据和推理链是否能推出预期答案。
3. 预期答案是否唯一。
4. query 是否没有直接泄露答案。
5. selected_evidence_indices 使用搜索证据中的 0-based index。

只输出 JSON，不要输出解释。格式：
{{
  "is_valid": true,
  "is_answer_supported": true,
  "is_unique": true,
  "confidence": 0.0,
  "reason": "...",
  "problems": ["..."],
  "selected_evidence_indices": [0, 1]
}}
"""
        response = self.gpt_client.chat(prompt=prompt)
        response.raise_for_error()
        data = extract_json(response.content)
        if not isinstance(data, dict):
            raise ValueError("final validation response is not a JSON object")

        selected_indices = data.get("selected_evidence_indices") or []
        selected_evidence = []
        if isinstance(selected_indices, list):
            for index in selected_indices:
                if isinstance(index, int) and 0 <= index < len(evidence):
                    selected_evidence.append(evidence[index])

        if not selected_evidence:
            selected_evidence = evidence[: min(5, len(evidence))]

        problems = data.get("problems") if isinstance(data.get("problems"), list) else []
        return FinalValidation(
            is_valid=bool(data.get("is_valid")),
            is_answer_supported=bool(data.get("is_answer_supported")),
            is_unique=bool(data.get("is_unique")),
            confidence=self._safe_float(data.get("confidence"), default=0.0),
            reason=str(data.get("reason") or ""),
            problems=[str(item) for item in problems],
            evidence=selected_evidence,
            raw=data,
        )

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def read_answers(args: argparse.Namespace) -> List[str]:
    answers = []
    if args.answer:
        answers.append(args.answer)

    if args.answers_file:
        with open(args.answers_file, "r", encoding="utf-8") as file_obj:
            for line in file_obj:
                line = line.strip()
                if line:
                    answers.append(line)

    if not answers:
        raise ValueError("请通过 --answer 或 --answers-file 提供答案")
    return answers


def build_config(args: argparse.Namespace) -> SynthesisConfig:
    return SynthesisConfig(
        target_hops=args.hops,
        max_candidates_per_hop=args.max_candidates,
        max_retry_per_hop=args.max_retries_per_hop,
        search_engines=args.search_engines,
        search_results_per_engine=args.search_results_per_engine,
        min_hop_confidence=args.min_hop_confidence,
        min_final_confidence=args.min_final_confidence,
        enable_fuzzification=not args.no_fuzzification,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize complex query-answer data from answers.")
    parser.add_argument("--answer", help="single answer to synthesize from")
    parser.add_argument("--answers-file", help="file with one answer per line")
    parser.add_argument("--output", default="synthetic_samples.jsonl", help="output jsonl file")
    parser.add_argument("--hops", type=int, default=2, help="target hop count")
    parser.add_argument("--max-candidates", type=int, default=5, help="candidate hops per retry")
    parser.add_argument("--max-retries-per-hop", type=int, default=3, help="retry count per hop")
    parser.add_argument(
        "--search-engines",
        nargs="+",
        default=list(DEFAULT_SEARCH_ENGINES),
        help="search engines, e.g. google bing baidu",
    )
    parser.add_argument("--search-results-per-engine", type=int, default=5)
    parser.add_argument("--min-hop-confidence", type=float, default=0.75)
    parser.add_argument("--min-final-confidence", type=float, default=0.75)
    parser.add_argument("--no-fuzzification", action="store_true")
    args = parser.parse_args()

    answers = read_answers(args)
    config = build_config(args)

    with DataSynthesizer(config=config) as synthesizer:
        with open(args.output, "a", encoding="utf-8") as output_file:
            for index, answer in enumerate(answers, start=1):
                print(f"[{index}/{len(answers)}] synthesize answer: {answer}")
                sample = synthesizer.synthesize(answer)
                output_file.write(json.dumps(sample.to_dict(), ensure_ascii=False) + "\n")
                output_file.flush()

                print(
                    f"  success={sample.success} "
                    f"hops={sample.hop_count} "
                    f"query={sample.query or '<EMPTY>'}"
                )
                if sample.error:
                    print(f"  error={sample.error}")

    print(f"saved to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
