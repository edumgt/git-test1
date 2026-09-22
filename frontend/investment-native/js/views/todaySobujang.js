import { marketRankingsView } from './todayGainers.js';

export function todaySobujangView(container) {
  marketRankingsView(container, {
    id: 'sobujang',
    title: '금일 소부장 종목 TOP 20',
    icon: 'fa-microchip',
    description: '국내 반도체 소재·부품·장비 대표 종목 20개 중 오늘 등락률이 높은 순서입니다. 전체 소부장 시장을 포괄하지 않는 학습용 참고 순위입니다.',
    endpoint: '/api/market/top-sobujang',
    loadingText: '오늘의 소부장 등락률을 불러오는 중…',
    note: 'Yahoo Finance 시세(약 15분 지연) 기준이며, 장중에는 순위가 계속 바뀝니다. 소부장 종목은 고객사 투자·반도체 업황·환율·수주 공시에 민감할 수 있으므로, 등락률만으로 투자 판단을 내리지 마세요.',
  });
}
