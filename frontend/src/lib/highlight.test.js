import { describe, expect, it } from 'vitest';
import {
	bestSentence,
	citingSentences,
	contentWords,
	excerpt,
	splitSentences
} from './highlight.js';

const passage =
	'4.1 Eligibility. Students are assessed through continuous evaluation. ' +
	'A student must have at least 75% attendance in each course to sit the end-term examination. ' +
	'Shortage may be condoned on medical grounds.';

const answer =
	'You need at least 75% attendance in each course for the end-term exam [1]. ' +
	'Shortages can be condoned on medical grounds [2].';

describe('contentWords', () => {
	it('keeps content words and numbers, drops stopwords and short words', () => {
		expect([...contentWords('The fee is ₹ 1,500 and you must pay by 15 Jan.')]).toEqual([
			'fee',
			'1,500',
			'pay',
			'15',
			'jan'
		]);
	});
});

describe('splitSentences', () => {
	it('splits at sentence ends and newlines and keeps every character', () => {
		const text = 'First one. Second (really)! Third?\nFourth line\nFifth';
		const sentences = splitSentences(text);
		expect(sentences).toEqual([
			'First one. ',
			'Second (really)! ',
			'Third?\n',
			'Fourth line\n',
			'Fifth'
		]);
		expect(sentences.join('')).toBe(text);
	});

	it('does not split decimals', () => {
		expect(splitSentences('CGPA of 7.5 or more. Next.')).toEqual([
			'CGPA of 7.5 or more. ',
			'Next.'
		]);
	});
});

describe('citingSentences', () => {
	it('returns the sentences that cite [n], without markers', () => {
		expect(citingSentences(answer, 1)).toEqual([
			'You need at least 75% attendance in each course for the end-term exam.'
		]);
		expect(citingSentences(answer, 3)).toEqual([]);
	});
});

describe('bestSentence', () => {
	it('picks the passage sentence that shares the most words', () => {
		const range = bestSentence(passage, citingSentences(answer, 1));
		expect(passage.slice(range.start, range.end)).toBe(
			'A student must have at least 75% attendance in each course to sit the end-term examination.'
		);
	});

	it('returns null when the overlap is too small to trust', () => {
		expect(bestSentence(passage, ['Parking near the library'])).toBeNull();
		expect(bestSentence(passage, [])).toBeNull();
	});
});

describe('excerpt', () => {
	it('highlights the cited sentence with its context', () => {
		const segments = excerpt(passage, answer, 2);
		expect(segments.find((s) => s.mark).text).toBe('Shortage may be condoned on medical grounds.');
		expect(segments.map((s) => s.text).join('')).toBe(passage);
	});

	it('cuts long passages around the sentence with ellipses', () => {
		const filler = 'Unrelated words fill this space again and again. '.repeat(20);
		const long = `${filler}A student must have 75% attendance in each course. ${filler}`;
		const segments = excerpt(long, answer, 1, { context: 60 });
		expect(segments[0].text.startsWith('… ')).toBe(true);
		expect(segments.at(-1).text.endsWith(' …')).toBe(true);
		expect(segments.find((s) => s.mark).text).toBe(
			'A student must have 75% attendance in each course.'
		);
		expect(segments.map((s) => s.text).join('').length).toBeLessThan(long.length);
	});

	it('shows the start of the passage when nothing matches', () => {
		const segments = excerpt(passage, 'Something else entirely [1].', 1, { context: 20 });
		expect(segments).toHaveLength(1);
		expect(segments[0].mark).toBe(false);
		expect(segments[0].text.startsWith('4.1 Eligibility.')).toBe(true);
		expect(segments[0].text.endsWith(' …')).toBe(true);
	});

	it('collapses runs of spaces and handles empty passages', () => {
		expect(excerpt('a   b\t\tc', '', 1)).toEqual([{ text: 'a b c', mark: false }]);
		expect(excerpt('', answer, 1)).toEqual([]);
		expect(excerpt(null, answer, 1)).toEqual([]);
	});
});
