import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

import '../advice_api.dart';
import '../api_config.dart';
import '../home_data.dart';
import '../user_storage.dart';
import '../widgets/ecowatt_widgets.dart';

class BillsScreen extends StatefulWidget {
  const BillsScreen({super.key});

  @override
  State<BillsScreen> createState() => _BillsScreenState();
}

class _BillsScreenState extends State<BillsScreen> {
  List<Map<String, dynamic>> bills = [];
  Map<String, dynamic>? selectedHome;

  bool isLoading = true;

  // Same FastAPI backend as the advice endpoints (see api_config.dart).
  static const String analyzeBillUrl = '${ApiConfig.baseUrl}/analyze-bill';

  static const List<String> months = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];

  static const List<String> years = [
    '2024',
    '2025',
    '2026',
    '2027',
    '2028',
    '2029',
    '2030',
  ];

  @override
  void initState() {
    super.initState();
    _loadBills();
  }

  Future<void> _loadBills() async {
    final home = await UserStorage.getSelectedHome();

    if (!mounted) return;

    if (home == null) {
      setState(() {
        selectedHome = null;
        bills = [];
        isLoading = false;
      });

      return;
    }

    final rawBills = home['bills'];

    final loadedBills = rawBills is List
        ? rawBills.map((bill) => Map<String, dynamic>.from(bill)).toList()
        : <Map<String, dynamic>>[];

    if (!mounted) return;

    setState(() {
      selectedHome = home;
      bills = loadedBills;
      isLoading = false;
    });
  }

  /// Saves the bills and returns the ids of newly inserted ones.
  Future<List<String>> _saveBills() async {
    final home = await UserStorage.getSelectedHome();

    if (home == null) return [];

    final updatedHome = Map<String, dynamic>.from(home);

    updatedHome['bills'] = bills;

    final newBillIds = await UserStorage.updateHome(updatedHome);

    if (!mounted) return newBillIds;

    setState(() {
      selectedHome = updatedHome;
    });

    return newBillIds;
  }

  /// Asks the backend to validate the bill, compare it with similar homes and
  /// generate advice. The bill is already saved, so a failure here is not fatal.
  Future<void> _requestAdvice(String billId, {bool edited = false}) async {
    try {
      final status = await AdviceApi.analyzeBill(billId);
      if (edited && status == 'kept' && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Bill analysis updated. Its advice was kept because you already applied some of it.',
            ),
            duration: Duration(seconds: 5),
          ),
        );
      }
    } on AdviceApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message),
          backgroundColor: Colors.orange,
          duration: const Duration(seconds: 6),
        ),
      );
    } catch (_) {
      // Backend unreachable: the bill stays saved; advice can be requested later.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ecowattPageBg,
      body: RefreshIndicator(
        color: const Color(0xFF08A045),
        onRefresh: _loadBills,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.zero,
          children: [
            EcowattPageHeader(
              title: 'Bills History',
              subtitle: 'Track your monthly electricity bills',
              children: [
                if (selectedHome != null) ...[
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      const Icon(
                        Icons.home_outlined,
                        color: Colors.white70,
                        size: 16,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        selectedHome!['homeName'] ?? 'Home',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
            EcowattOverlap(
              child: isLoading
                  ? const Padding(
                      padding: EdgeInsets.only(top: 80),
                      child: Center(
                        child: CircularProgressIndicator(
                          color: Color(0xFF08A045),
                        ),
                      ),
                    )
                  : Column(
                      children: [
                        // ADD BILL BUTTON
                        GestureDetector(
                          onTap: () => _showAddBillDialog(context),
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 20),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(14),
                              boxShadow: const [
                                BoxShadow(
                                  color: Colors.black12,
                                  blurRadius: 10,
                                  offset: Offset(0, 4),
                                ),
                              ],
                            ),
                            child: const Center(
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(
                                    Icons.add_circle_outline,
                                    color: Color(0xFF08A045),
                                  ),
                                  SizedBox(width: 10),
                                  Text(
                                    'Add New Bill',
                                    style: TextStyle(
                                      color: Color(0xFF08A045),
                                      fontWeight: FontWeight.w600,
                                      fontSize: 16,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),

                        const SizedBox(height: 20),

                        if (bills.isEmpty)
                          _emptyBillsState()
                        else
                          ...bills.map((bill) => _billItem(bill)),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _emptyBillsState() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(28, 48, 28, 48),
      child: Column(
        children: [
          Container(
            width: 74,
            height: 74,
            decoration: const BoxDecoration(
              color: Color(0x1408A045),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.receipt_long_outlined,
              color: Color(0xFF08A045),
              size: 36,
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'No bills yet',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            'Add your first bill to start tracking your consumption and receive smart insights.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey, fontSize: 14, height: 1.5),
          ),
        ],
      ),
    );
  }

  Widget _billItem(Map<String, dynamic> bill) {
    final title = '${bill['title'] ?? ''}';
    final usage = '${bill['usage'] ?? ''}';
    final price = '${bill['price'] ?? ''}';
    return GestureDetector(
      onTap: () => _showAddBillDialog(context, existing: bill),
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.black12),
          boxShadow: const [
            BoxShadow(
              color: Colors.black12,
              blurRadius: 6,
              offset: Offset(0, 3),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: const BoxDecoration(
                color: Color(0x1408A045),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.receipt_long, color: Color(0xFF08A045)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 16,
                    ),
                  ),
                  Text(
                    usage,
                    style: const TextStyle(color: Colors.grey, fontSize: 13),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  price,
                  style: const TextStyle(
                    color: Color(0xFF08A045),
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Text(
                  'SAR',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
            IconButton(
              tooltip: 'Edit bill',
              icon: const Icon(
                Icons.edit_outlined,
                color: Colors.grey,
                size: 20,
              ),
              onPressed: () => _showAddBillDialog(context, existing: bill),
            ),
          ],
        ),
      ),
    );
  }

  /// Add a new bill, or edit [existing] (same form, pre-filled).
  void _showAddBillDialog(
    BuildContext context, {
    Map<String, dynamic>? existing,
  }) {
    final isEdit = existing != null;
    final originalAmount = isEdit ? _formatApiNumber(existing['price']) : '';
    final originalConsumption = isEdit
        ? _formatApiNumber(existing['consumption'])
        : '';
    final amountController = TextEditingController(text: originalAmount);
    final consumptionController = TextEditingController(
      text: originalConsumption,
    );

    String? selectedMonth = isEdit && months.contains('${existing['month']}')
        ? '${existing['month']}'
        : null;
    String? selectedYear = isEdit && years.contains('${existing['year']}')
        ? '${existing['year']}'
        : null;
    final originalMonth = selectedMonth;
    final originalYear = selectedYear;

    bool isAnalyzing = false;
    bool imageWasAnalyzed = false;
    String? analysisMessage;
    String analysisType = '';

    String? selectedImageName;

    showDialog(
      context: context,
      barrierDismissible: !isAnalyzing,
      builder: (dialogContext) {
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(horizontal: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: StatefulBuilder(
              builder: (context, setDialogState) {
                // Validation errors are shown inside the form: a SnackBar would
                // appear on the page underneath, hidden by this dialog.
                void showFormError(String message) {
                  setDialogState(() {
                    analysisType = 'error';
                    analysisMessage = message;
                  });
                }

                Future<void> pickAndAnalyzeBill() async {
                  final picker = ImagePicker();

                  final pickedImage = await picker.pickImage(
                    source: ImageSource.gallery,
                    imageQuality: 100,
                  );

                  if (pickedImage == null) {
                    return;
                  }

                  setDialogState(() {
                    isAnalyzing = true;
                    imageWasAnalyzed = false;
                    selectedImageName = pickedImage.name;
                    analysisMessage = null;
                    analysisType = '';
                  });

                  try {
                    final bytes = await pickedImage.readAsBytes();

                    final request = http.MultipartRequest(
                      'POST',
                      Uri.parse(analyzeBillUrl),
                    );

                    // The backend now requires the signed-in user's session.
                    request.headers.addAll(AdviceApi.authHeaders());

                    request.files.add(
                      http.MultipartFile.fromBytes(
                        'file',
                        bytes,
                        filename: pickedImage.name,
                      ),
                    );

                    // Never spin forever: a GPU scan takes ~10 s; give up after 90 s.
                    final streamedResponse = await request.send().timeout(
                      const Duration(seconds: 90),
                    );

                    final response = await http.Response.fromStream(
                      streamedResponse,
                    ).timeout(const Duration(seconds: 90));

                    if (response.statusCode != 200) {
                      String errorMessage =
                          'We could not analyze this image. Please upload a clear electricity bill.';

                      try {
                        final errorData = jsonDecode(response.body);

                        if (errorData['detail'] != null) {
                          errorMessage = errorData['detail'].toString();
                        }
                      } catch (_) {}

                      if (!dialogContext.mounted) {
                        return;
                      }

                      setDialogState(() {
                        isAnalyzing = false;
                        imageWasAnalyzed = false;
                        analysisType = 'error';
                        analysisMessage = errorMessage;
                      });

                      return;
                    }

                    final data = jsonDecode(response.body);

                    final success = data['success'] == true;

                    if (!success) {
                      if (!dialogContext.mounted) {
                        return;
                      }

                      setDialogState(() {
                        isAnalyzing = false;
                        imageWasAnalyzed = false;
                        analysisType = 'error';
                        analysisMessage =
                            data['message'] ??
                            'We could not recognize this bill. Please upload a clear electricity bill or enter the information manually.';
                      });

                      return;
                    }

                    final extractedMonth = data['month']?.toString();

                    final amount = data['amount_due'];

                    final consumption = data['consumption'];

                    String? detectedMonth;
                    String? detectedYear;

                    if (extractedMonth != null &&
                        extractedMonth.trim().isNotEmpty) {
                      final parts = extractedMonth.trim().split(RegExp(r'\s+'));

                      if (parts.isNotEmpty && months.contains(parts.first)) {
                        detectedMonth = parts.first;
                      }

                      if (parts.length >= 2 && years.contains(parts.last)) {
                        detectedYear = parts.last;
                      }
                    }

                    if (!dialogContext.mounted) {
                      return;
                    }

                    setDialogState(() {
                      if (amount != null) {
                        amountController.text = _formatApiNumber(amount);
                      }

                      if (consumption != null) {
                        consumptionController.text = _formatApiNumber(
                          consumption,
                        );
                      }

                      if (detectedMonth != null) {
                        selectedMonth = detectedMonth;
                      }

                      if (detectedYear != null) {
                        selectedYear = detectedYear;
                      }

                      isAnalyzing = false;
                      imageWasAnalyzed = true;

                      final status = data['status']?.toString();

                      if (status == 'partial') {
                        analysisType = 'warning';
                        analysisMessage =
                            'Some information could not be detected. Please review the extracted information and complete any missing fields.';
                      } else {
                        analysisType = 'success';
                        analysisMessage =
                            'Bill analyzed successfully. Please review the extracted information before confirming.';
                      }
                    });
                  } catch (e) {
                    if (!dialogContext.mounted) {
                      return;
                    }

                    setDialogState(() {
                      isAnalyzing = false;
                      imageWasAnalyzed = false;
                      analysisType = 'error';
                      analysisMessage = e is TimeoutException
                          ? 'Scanning is taking too long right now. Please enter the bill details manually, or try again in a minute.'
                          : 'Unable to connect to the bill analysis service. Make sure the EcoWatt API is running, then try again.';
                    });
                  }
                }

                return SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              isEdit ? 'Edit Bill' : 'Add New Bill',
                              style: const TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          IconButton(
                            onPressed: isAnalyzing
                                ? null
                                : () => Navigator.pop(dialogContext),
                            icon: const Icon(Icons.close),
                          ),
                        ],
                      ),

                      const SizedBox(height: 8),

                      const Text(
                        'Upload your electricity bill to fill the information automatically, or enter it manually.',
                        style: TextStyle(
                          color: Colors.grey,
                          fontSize: 13,
                          height: 1.4,
                        ),
                      ),

                      const SizedBox(height: 18),

                      // UPLOAD BILL IMAGE
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF7FBF8),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: const Color(0x3308A045)),
                        ),
                        child: Column(
                          children: [
                            const Icon(
                              Icons.document_scanner_outlined,
                              color: Color(0xFF08A045),
                              size: 34,
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              'Upload Bill Image',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text(
                              'Upload a clear screenshot or photo of your electricity bill.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.grey,
                                fontSize: 12,
                              ),
                            ),
                            const SizedBox(height: 12),

                            SizedBox(
                              width: double.infinity,
                              height: 44,
                              child: OutlinedButton.icon(
                                onPressed: isAnalyzing
                                    ? null
                                    : pickAndAnalyzeBill,
                                style: OutlinedButton.styleFrom(
                                  side: const BorderSide(
                                    color: Color(0xFF08A045),
                                  ),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(9),
                                  ),
                                ),
                                icon: isAnalyzing
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Color(0xFF08A045),
                                        ),
                                      )
                                    : const Icon(
                                        Icons.upload_file_outlined,
                                        color: Color(0xFF08A045),
                                      ),
                                label: Text(
                                  isAnalyzing
                                      ? 'Analyzing Bill...'
                                      : imageWasAnalyzed
                                      ? 'Upload Another Image'
                                      : 'Choose Image',
                                  style: const TextStyle(
                                    color: Color(0xFF08A045),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                            ),

                            if (selectedImageName != null) ...[
                              const SizedBox(height: 10),
                              Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  const Icon(
                                    Icons.image_outlined,
                                    size: 15,
                                    color: Colors.grey,
                                  ),
                                  const SizedBox(width: 5),
                                  Flexible(
                                    child: Text(
                                      selectedImageName!,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                        color: Colors.grey,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),

                      if (analysisMessage != null) ...[
                        const SizedBox(height: 14),
                        _analysisMessageBox(
                          type: analysisType,
                          message: analysisMessage!,
                        ),
                      ],

                      const SizedBox(height: 20),

                      const Text(
                        'Bill Amount (SAR)',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),

                      const SizedBox(height: 8),

                      TextField(
                        controller: amountController,
                        enabled: !isAnalyzing,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        inputFormatters: [
                          FilteringTextInputFormatter.allow(
                            RegExp(r'^\d*\.?\d{0,2}'),
                          ),
                        ],
                        decoration: InputDecoration(
                          hintText: 'Enter bill amount',
                          filled: true,
                          fillColor: const Color(0xFFF3F3F5),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),

                      const SizedBox(height: 16),

                      const Text(
                        'Consumption (kWh)',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),

                      const SizedBox(height: 8),

                      TextField(
                        controller: consumptionController,
                        enabled: !isAnalyzing,
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        inputFormatters: [
                          FilteringTextInputFormatter.allow(
                            RegExp(r'^\d*\.?\d{0,2}'),
                          ),
                        ],
                        decoration: InputDecoration(
                          hintText: 'Enter consumption',
                          filled: true,
                          fillColor: const Color(0xFFF3F3F5),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),

                      const SizedBox(height: 16),

                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Month',
                                  style: TextStyle(fontWeight: FontWeight.w600),
                                ),
                                const SizedBox(height: 8),
                                DropdownButtonFormField<String>(
                                  isExpanded: true,
                                  // key: re-create the field when the bill scanner sets the month
                                  key: ValueKey(selectedMonth),
                                  initialValue: selectedMonth,
                                  hint: const Text(
                                    'Select month',
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  decoration: InputDecoration(
                                    filled: true,
                                    fillColor: const Color(0xFFF3F3F5),
                                    border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(10),
                                      borderSide: BorderSide.none,
                                    ),
                                  ),
                                  items: months
                                      .map(
                                        (month) => DropdownMenuItem(
                                          value: month,
                                          child: Text(month),
                                        ),
                                      )
                                      .toList(),
                                  onChanged: isAnalyzing
                                      ? null
                                      : (value) {
                                          setDialogState(() {
                                            selectedMonth = value;
                                          });
                                        },
                                ),
                              ],
                            ),
                          ),

                          const SizedBox(width: 10),

                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Year',
                                  style: TextStyle(fontWeight: FontWeight.w600),
                                ),
                                const SizedBox(height: 8),
                                DropdownButtonFormField<String>(
                                  // key: re-create the field when the value is set from code (e.g. by the bill scanner)
                                  key: ValueKey(selectedYear),
                                  initialValue: selectedYear,
                                  isExpanded: true,
                                  hint: const Text('Year'),
                                  decoration: InputDecoration(
                                    filled: true,
                                    fillColor: const Color(0xFFF3F3F5),
                                    border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(10),
                                      borderSide: BorderSide.none,
                                    ),
                                  ),
                                  items: years
                                      .map(
                                        (year) => DropdownMenuItem(
                                          value: year,
                                          child: Text(year),
                                        ),
                                      )
                                      .toList(),
                                  onChanged: isAnalyzing
                                      ? null
                                      : (value) {
                                          setDialogState(() {
                                            selectedYear = value;
                                          });
                                        },
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 10),

                      const Text(
                        'Please review the information above before adding the bill. You can edit any value if needed.',
                        style: TextStyle(
                          color: Colors.grey,
                          fontSize: 12,
                          height: 1.4,
                        ),
                      ),

                      const SizedBox(height: 20),

                      SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF08A045),
                            disabledBackgroundColor: Colors.grey[300],
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          onPressed: isAnalyzing
                              ? null
                              : () async {
                                  final amount = amountController.text.trim();

                                  final consumption = consumptionController.text
                                      .trim();

                                  if (amount.isEmpty ||
                                      consumption.isEmpty ||
                                      selectedMonth == null ||
                                      selectedYear == null) {
                                    showFormError(
                                      'Please review and fill in all bill fields',
                                    );

                                    return;
                                  }

                                  final parsedAmount = double.tryParse(amount);

                                  final parsedConsumption = double.tryParse(
                                    consumption,
                                  );

                                  if (parsedAmount == null ||
                                      parsedAmount <= 0 ||
                                      parsedConsumption == null ||
                                      parsedConsumption <= 0) {
                                    showFormError(
                                      'Please enter valid bill amount and consumption values',
                                    );

                                    return;
                                  }

                                  // Same rule as the backend: a bill whose price does not match its
                                  // kWh under the SEC residential tariff is almost always a typo.
                                  // Catch it here so a wrong bill is never saved without analysis.
                                  if (HomeData.tariffInconsistent(
                                    parsedConsumption,
                                    parsedAmount,
                                  )) {
                                    final expected = HomeData.expectedCostSar(
                                      parsedConsumption,
                                    ).round();
                                    showFormError(
                                      '${formatInt(parsedConsumption)} kWh should cost about '
                                      '$expected SAR, but the amount is $amount SAR. '
                                      'Please check both values.',
                                    );
                                    return;
                                  }

                                  final newTitle =
                                      '$selectedMonth $selectedYear';

                                  final alreadyExists = bills.any(
                                    (bill) =>
                                        bill['title'] == newTitle &&
                                        bill['id'] != existing?['id'],
                                  );

                                  if (alreadyExists) {
                                    showFormError(
                                      '$newTitle is already added. Tap that bill in the list to edit it.',
                                    );

                                    return;
                                  }

                                  final unchanged =
                                      isEdit &&
                                      amount == originalAmount &&
                                      consumption == originalConsumption &&
                                      selectedMonth == originalMonth &&
                                      selectedYear == originalYear;
                                  if (unchanged) {
                                    Navigator.pop(dialogContext);
                                    return;
                                  }

                                  final entry = <String, dynamic>{
                                    'id': isEdit
                                        ? existing['id']
                                        : 'bill_${DateTime.now().millisecondsSinceEpoch}',
                                    'title': newTitle,
                                    'month': selectedMonth,
                                    'year': selectedYear,
                                    'usage': '$consumption kWh',
                                    'consumption': consumption,
                                    'price': amount,
                                  };

                                  setState(() {
                                    if (isEdit) {
                                      final i = bills.indexWhere(
                                        (b) => b['id'] == existing['id'],
                                      );
                                      if (i >= 0) bills[i] = entry;
                                    } else {
                                      bills.insert(0, entry);
                                    }
                                  });

                                  final newBillIds = await _saveBills();

                                  if (!mounted) {
                                    return;
                                  }

                                  if (dialogContext.mounted) {
                                    Navigator.pop(dialogContext);
                                  }

                                  // Fire and forget: validates the bill, updates
                                  // its analysis and (re)generates advice.
                                  final toAnalyze = isEdit
                                      ? ['${existing['id']}']
                                      : newBillIds;
                                  for (final id in toAnalyze) {
                                    _requestAdvice(id, edited: isEdit);
                                  }

                                  ScaffoldMessenger.of(
                                    this.context,
                                  ).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        isEdit
                                            ? '$newTitle has been updated'
                                            : '$newTitle has been added',
                                      ),
                                      backgroundColor: const Color(0xFF08A045),
                                    ),
                                  );
                                },
                          child: Text(
                            isEdit ? 'Save Changes' : 'Confirm & Add Bill',
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  Widget _analysisMessageBox({required String type, required String message}) {
    Color backgroundColor;
    Color borderColor;
    Color iconColor;
    IconData icon;

    if (type == 'success') {
      backgroundColor = const Color(0xFFF0FDF4);
      borderColor = const Color(0xFF86EFAC);
      iconColor = const Color(0xFF16A34A);
      icon = Icons.check_circle_outline;
    } else if (type == 'warning') {
      backgroundColor = const Color(0xFFFFFBEB);
      borderColor = const Color(0xFFFCD34D);
      iconColor = const Color(0xFFD97706);
      icon = Icons.warning_amber_rounded;
    } else {
      backgroundColor = const Color(0xFFFEF2F2);
      borderColor = const Color(0xFFFCA5A5);
      iconColor = const Color(0xFFDC2626);
      icon = Icons.error_outline;
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: iconColor, size: 21),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color: iconColor,
                fontSize: 13,
                height: 1.35,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatApiNumber(dynamic value) {
    if (value == null) return '';

    final number = double.tryParse(value.toString());

    if (number == null) {
      return value.toString();
    }

    if (number == number.roundToDouble()) {
      return number.toInt().toString();
    }

    return number
        .toStringAsFixed(2)
        .replaceFirst(RegExp(r'0+$'), '')
        .replaceFirst(RegExp(r'\.$'), '');
  }
}
