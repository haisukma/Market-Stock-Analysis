from playwright.sync_api import sync_playwright
import time

def get_tradingview_full_data(ticker):
    def get_keystats_value(page):
        try:
            info_map = {}

            # Ambil container khusus company info
            company_section = page.locator('div[data-an-widget-id="key-stats-id"]')
            blocks = company_section.locator('div[class^="blockContent-"]')
            count = blocks.count()

            # Label urutan yang benar (sesuai HTML-nya)
            label_map = {
                0: "Market capitalization",
                1: "Dividend yield (indicated)",
                2: "Price to earning Ratio (TTM)",
                3: "Basic EPS (TTM)",
                4: "Net Income (FY)",
                5: "Revenue (FY)",
                6: "Shares float",
                7: "Beta (1Y)"
            }

            for i in range(count):
                try:
                    block = blocks.nth(i)
                    value_node = block.locator('div[class^="apply-overflow-tooltip value-"]').first
                    value = value_node.inner_text().strip()
                    label = label_map.get(i, f"Unknown_{i}")
                    info_map[label] = value
                except:
                    continue

            return info_map
        except Exception as e:
            print(f"⚠️ Gagal ambil info:", e)
            return {}
    def get_employees_value(page):
        try:
            info_map = {}

            # Ambil container khusus company info
            company_section = page.locator('div[data-an-widget-id="employees-section"]')
            blocks = company_section.locator('div[class^="blockContent-"]')
            count = blocks.count()

            # Label urutan yang benar (sesuai HTML-nya)
            label_map = {
                0: "Employees (FY)"
            }

            for i in range(count):
                try:
                    block = blocks.nth(i)
                    value_node = block.locator('div[class^="apply-overflow-tooltip value-"]').first
                    value = value_node.inner_text().strip()
                    label = label_map.get(i, f"Unknown_{i}")
                    info_map[label] = value
                except:
                    continue

            return info_map
        except Exception as e:
            print(f"⚠️ Gagal ambil info:", e)
            return {}

    def extract_company_info(page):
        try:
            info_map = {}

            # Ambil container khusus company info
            company_section = page.locator('div[data-an-widget-id="company-info-id"]')
            blocks = company_section.locator('div[class^="blockContent-"]')
            count = blocks.count()

            # Label urutan yang benar (sesuai HTML-nya)
            label_map = {
                0: "Sector",
                1: "Industry",
                2: "Website",
                3: "Location",
                4: "Founded",
                5: "ISIN",
                6: "BBG"
            }

            for i in range(count):
                try:
                    block = blocks.nth(i)
                    value_node = block.locator('div[class^="apply-overflow-tooltip value-"]').first
                    value = value_node.inner_text().strip()
                    label = label_map.get(i, f"Unknown_{i}")
                    info_map[label] = value
                except:
                    continue

            return info_map
        except Exception as e:
            print(f"⚠️ Gagal ambil info:", e)
            return {}

    # def get_founded_value(page):
    #     try:
    #         element = page.locator("text=Founded").first
    #         parent = element.locator("xpath=..")
    #         sibling = parent.locator("xpath=following-sibling::div[1]")
    #         value = sibling.inner_text()
    #         print(f"🎂 Founded: {value}")
    #         return value.strip()
    #     except Exception as e:
    #         print("⚠️ Gagal ambil Founded:", e)
    #         return "N/A"

    def get_description(page):
        try:
            # Scroll ke bawah supaya deskripsi muncul
            page.mouse.wheel(0, 2000)
            time.sleep(2)

            # Ambil elemen div dengan class deskripsi
            desc_div = page.locator('div[class*="truncatedBlockText"]').first
            description = desc_div.inner_text().strip()
            print("📝 Deskripsi ditemukan.")
            return description
        except Exception as e:
            print("⚠️ Gagal ambil deskripsi:", e)
            return "N/A"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        tv_ticker = ticker 
        base_url = f"https://www.tradingview.com/symbols/{tv_ticker}/"
        technical_url = f"{base_url}technicals/"

        print(f"🔍 Mengunjungi halaman utama: {base_url}")
        page.goto(base_url, timeout=60000)
        time.sleep(3)

        description = get_description(page)
        company_info = extract_company_info(page)
        sector = company_info.get("Sector", "N/A")
        industry = company_info.get("Industry", "N/A")
        # founded = company_info.get("Founded", "N/A")
        employees = get_employees_value(page).get("Employees (FY)", "N/A")
        key_stats_info = get_keystats_value(page)
        market_capitalization = key_stats_info.get("Market capitalization", "N/A")
        dividend_yield = key_stats_info.get("Dividend yield (indicated)", "N/A")
        price_earning = key_stats_info.get("Price to earning Ratio (TTM)", "N/A")
        basic_EPS = key_stats_info.get("Basic EPS (TTM)", "N/A")
        net_income = key_stats_info.get("Net Income (FY)", "N/A")
        revenue = key_stats_info.get("Revenue (FY)", "N/A")
        shares_float = key_stats_info.get("Shares float", "N/A")
        beta = key_stats_info.get("Beta (1Y)", "N/A")



        print(f"🔁 Beralih ke halaman technicals: {technical_url}")
        page.goto(technical_url, timeout=60000)
        page.wait_for_timeout(3000)


        browser.close()

        data = {
            "ticker": ticker,
            "company_info": {
                "description": description,
                "sector": sector,
                "industry": industry,
                "employees": employees,
                "market_capitalization": market_capitalization,
                "dividend_yield": dividend_yield,
                "price_earning": price_earning,
                "basic_EPS": basic_EPS,
                "net_income": net_income,
                "revenue": revenue,
                "shares_float": shares_float,
                "beta": beta
                # "founded": founded
            }
        }

        print("\n🎯 HASIL:")
        print(data)
        return data


# Jalankan
if __name__ == "__main__":
    get_tradingview_full_data("ANTM")